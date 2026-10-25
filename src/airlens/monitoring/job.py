"""Job monitoring (mingguan lewat scheduler; manual lewat `make monitor`).

Tidak ada label benar dari pengguna, jadi yang dipantau adalah sinyal yang tersedia:
1. Drift input: fitur gambar + embedding CNN (PCA) dibanding data latih model production (PSI, KS).
2. Keyakinan, porsi "belum pasti", dan porsi foto ditolak, juga per minggu.
3. Selisih terhadap IQAir. PROKSI BERISIK: IQAir mengukur satu kota, foto hanya satu titik pandang.
4. Shadow: kesepakatan challenger vs production pada foto yang sama.
Hasil: baris monitoring_reports, laporan Markdown, peringatan ke log + webhook opsional.
"""

import json
import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import requests
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from airlens.aqi import aqi_to_category
from airlens.db.models import MonitoringReport, Prediction
from airlens.monitoring.drift import drift_table
from airlens.monitoring.signature import FEATURE_LABELS

logger = logging.getLogger("airlens.monitoring")


def load_reference(model_version: str, cache_dir: Path) -> dict | None:
    """Metadata model dari cache API (volume modelcache), mis. 'airlens-aqi/4' -> cache_dir/v4/metadata.json."""
    try:
        n = model_version.split("/")[1].split()[0]
        meta = json.loads((cache_dir / f"v{n}" / "metadata.json").read_text())
    except (IndexError, FileNotFoundError, ValueError):
        return None
    return meta


def _rate(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def compute(rows: list[Prediction], shadow: list[Prediction], meta: dict | None, cfg: dict) -> dict:
    th = cfg["monitoring"]["thresholds"]
    merge = cfg["data"]["class_merge"]
    classes = meta["classes"] if meta else []
    n = len(rows)
    rejected = [r for r in rows if r.status == "rejected"]
    accepted = [r for r in rows if r.status in ("ok", "uncertain")]
    conf = np.array([r.confidence for r in accepted if r.confidence is not None], float)
    weekly: dict[str, Counter] = {}
    for r in rows:
        wk = r.created_at.strftime("%G-W%V")
        weekly.setdefault(wk, Counter())[r.status] += 1
    report = {
        "n": n,
        "rejected_rate": _rate(len(rejected), n),
        "uncertain_rate": _rate(sum(r.status == "uncertain" for r in accepted), len(accepted)),
        "reject_reasons": dict(Counter(r.reject_reason for r in rejected)),
        "confidence": ({"mean": round(float(conf.mean()), 4),
                        **{f"p{q}": round(float(np.percentile(conf, q)), 4) for q in (10, 50, 90)},
                        "hist": np.histogram(conf, bins=10, range=(0, 1))[0].tolist()} if len(conf) else None),
        "weekly": {wk: {"n": sum(c.values()), "ditolak": _rate(c["rejected"], sum(c.values())),
                        "belum_pasti": _rate(c["uncertain"], c["ok"] + c["uncertain"])} for wk, c in sorted(weekly.items())},
    }

    # ---- drift: fitur gambar (semua foto yang punya statistik) + embedding (foto yang dianalisis)
    report["drift"] = {}
    ref = (meta or {}).get("monitoring_reference")
    if ref:
        cur = {f: [r.input_stats.get(f) for r in rows if r.input_stats and f in r.input_stats] for f in ref["features"]}
        report["drift"] = drift_table(ref["features"], cur)
        if ref.get("emb_proj"):
            embs = [r.input_stats["emb_pca"] for r in accepted if r.input_stats and r.input_stats.get("emb_pca")]
            if embs:
                arr = np.asarray(embs, float)
                cur_emb = {f"emb_pc{i + 1}": arr[:, i].tolist() for i in range(arr.shape[1])}
                report["drift"].update(drift_table(ref["emb_proj"], cur_emb))

    # ---- selisih IQAir (proksi berisik)
    diffs = []
    for r in rows:
        if r.status == "ok" and r.iqair_aqi_us is not None and r.predicted_class in classes:
            iq = aqi_to_category(r.iqair_aqi_us)
            iq = merge.get(iq, iq)
            if iq in classes:
                diffs.append(classes.index(r.predicted_class) - classes.index(iq))
    report["iqair"] = {"n": len(diffs), "sama_kategori": _rate(sum(d == 0 for d in diffs), len(diffs)),
                       "rata_selisih_absolut": round(float(np.mean(np.abs(diffs))), 3) if diffs else None,
                       "rata_selisih": round(float(np.mean(diffs)), 3) if diffs else None,
                       "catatan": "proksi berisik: IQAir tingkat kota, bukan titik foto"}

    # ---- shadow
    prod_by_job = {r.job_id: r for r in accepted if r.job_id}
    pairs = [(prod_by_job[s.job_id], s) for s in shadow if s.job_id in prod_by_job]
    report["shadow"] = {
        "n": len(pairs), "model": shadow[0].model_version if shadow else None,
        "sepakat_kelas": _rate(sum(p.predicted_class == s.predicted_class for p, s in pairs), len(pairs)),
        "belum_pasti_challenger": _rate(sum(s.status == "uncertain" for _, s in pairs), len(pairs)),
    }

    # ---- peringatan
    alerts = []
    enough = n >= th["min_samples"]
    if not enough:
        alerts.append({"type": "info", "message": f"Sampel {n} < {th['min_samples']}: drift tidak dinilai."})
    if meta is None:
        alerts.append({"type": "info", "message": "Metadata model production tidak ditemukan: drift tidak dinilai."})
    def flagged(d: dict) -> bool:
        return d["n"] >= th["min_samples"] and d["psi_adj"] >= th["psi_min"] and d["ks_p"] < th["ks_p"]

    # Fitur gambar: per fitur. Embedding: SATU penilaian (>= emb_min_fraction komponen bergeser), karena komponen
    # embedding juga bereaksi pada pemandangan baru; per komponen akan menyala tiap minggu (lihat DECISIONS.md).
    emb = {f: d for f, d in report["drift"].items() if f.startswith("emb_pc")}
    for f, d in report["drift"].items():
        if enough and not f.startswith("emb_pc") and flagged(d):
            alerts.append({"type": "drift", "feature": f, "psi": d["psi"], "psi_adj": d["psi_adj"], "ks_p": d["ks_p"],
                           "message": f"Drift pada {FEATURE_LABELS.get(f, f)}: PSI {d['psi']} (terkoreksi {d['psi_adj']}), "
                                      f"KS p={d['ks_p']} (median latih {d['ref_median']} -> sekarang {d['cur_median']})"})
    if enough and emb:
        hit = [f for f, d in emb.items() if flagged(d)]
        report["embedding_drift_fraction"] = round(len(hit) / len(emb), 3)
        if len(hit) / len(emb) >= th["emb_min_fraction"]:
            alerts.append({"type": "drift", "feature": "embedding", "components": hit,
                           "message": f"Drift pada embedding CNN: {len(hit)}/{len(emb)} komponen PCA bergeser"})
    if enough and (report["uncertain_rate"] or 0) > th["uncertain_rate"]:
        alerts.append({"type": "keyakinan", "message": f"Porsi 'belum pasti' {report['uncertain_rate']:.0%} > {th['uncertain_rate']:.0%}"})
    if enough and (report["rejected_rate"] or 0) > th["rejected_rate"]:
        alerts.append({"type": "penolakan", "message": f"Porsi foto ditolak {report['rejected_rate']:.0%} > {th['rejected_rate']:.0%}"})
    iq_n, iq_d = report["iqair"]["n"], report["iqair"]["rata_selisih_absolut"]
    if iq_n >= th["min_samples"] and iq_d is not None and iq_d > th["iqair_mean_abs_diff"]:
        alerts.append({"type": "iqair", "message": f"Rata-rata selisih kategori vs IQAir {iq_d} > {th['iqair_mean_abs_diff']} (proksi)"})
    report["alerts"] = alerts
    report["retrain_recommended"] = any(a["type"] in ("drift", "iqair") for a in alerts)
    return report


def to_markdown(report: dict, start: datetime, end: datetime, model_version: str | None) -> str:
    lines = [f"# Laporan monitoring AirLens", "",
             f"- Jendela: {start:%Y-%m-%d %H:%M} s.d. {end:%Y-%m-%d %H:%M} UTC",
             f"- Model production: {model_version or '-'}",
             f"- Prediksi: {report['n']} · ditolak {report['rejected_rate']} · belum pasti {report['uncertain_rate']}",
             f"- **Rekomendasi retraining: {'YA' if report['retrain_recommended'] else 'tidak'}**", "", "## Peringatan", ""]
    real = [a for a in report["alerts"] if a["type"] != "info"]
    lines += [f"- ⚠ {a['message']}" for a in real] or ["- Tidak ada."]
    lines += [f"- ℹ {a['message']}" for a in report["alerts"] if a["type"] == "info"]
    lines += ["", "## Drift input (vs data latih model production)", "",
              "| Fitur | PSI | PSI terkoreksi | KS | KS p | median latih | median sekarang | n |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for f, d in report["drift"].items():
        lines.append(f"| {FEATURE_LABELS.get(f, f)} | {d['psi']} | {d['psi_adj']} | {d['ks']} | {d['ks_p']} | "
                     f"{d['ref_median']} | {d['cur_median']} | {d['n']} |")
    c = report["confidence"]
    lines += ["", "## Keyakinan", "", (f"Rata-rata {c['mean']} · p10 {c['p10']} · median {c['p50']} · p90 {c['p90']}"
                                         if c else "Tidak ada prediksi yang dianalisis."), "",
              "| Minggu | n | ditolak | belum pasti |", "|---|---:|---:|---:|"]
    lines += [f"| {wk} | {w['n']} | {w['ditolak']} | {w['belum_pasti']} |" for wk, w in report["weekly"].items()]
    iq = report["iqair"]
    lines += ["", "## Selisih terhadap IQAir (proksi berisik)", "",
              "IQAir mengukur satu kota, sedangkan foto hanya satu titik pandang; selisih bukan kesalahan model yang pasti.", "",
              f"n {iq['n']} · kategori sama {iq['sama_kategori']} · rata-rata |selisih| {iq['rata_selisih_absolut']} kategori"]
    sh = report["shadow"]
    lines += ["", "## Shadow mode", "", f"Challenger: {sh['model'] or '-'} · n {sh['n']} · sepakat kelas {sh['sepakat_kelas']}"
              f" · belum pasti (challenger) {sh['belum_pasti_challenger']}", ""]
    return "\n".join(lines)


def run(engine: Engine, cfg: dict, cache_dir: Path, out_dir: Path, since: datetime | None = None,
        until: datetime | None = None, reference: dict | None = None, report_type: str = "mingguan") -> dict:
    until = until or datetime.now(timezone.utc)
    since = since or until - timedelta(days=cfg["monitoring"]["window_days"])
    with Session(engine) as s:
        rows = list(s.scalars(select(Prediction).where(Prediction.created_at >= since, Prediction.created_at < until,
                                                       Prediction.is_shadow.is_(False))))
        shadow = list(s.scalars(select(Prediction).where(Prediction.created_at >= since, Prediction.created_at < until,
                                                         Prediction.is_shadow.is_(True))))
    versions = Counter(r.model_version for r in rows if r.model_version and r.model_version != "tidak-tersedia")
    model_version = versions.most_common(1)[0][0] if versions else None
    meta = reference if reference is not None else (load_reference(model_version, cache_dir) if model_version else None)
    report = compute(rows, shadow, meta, cfg)

    with Session(engine) as s:
        row = MonitoringReport(report_type=report_type, window_start=since, window_end=until,
                               metrics={k: v for k, v in report.items() if k != "alerts"} | {"model_version": model_version},
                               alerts=report["alerts"], retrain_triggered=report["retrain_recommended"])
        s.add(row)
        s.commit()
        report["report_id"] = row.id
    out_dir.mkdir(parents=True, exist_ok=True)
    md = out_dir / f"monitoring_{until:%Y%m%d_%H%M%S}.md"
    md.write_text(to_markdown(report, since, until, model_version))
    report["markdown"] = str(md)

    real = [a for a in report["alerts"] if a["type"] != "info"]
    for a in real:
        logger.warning("PERINGATAN monitoring: %s", a["message"])
    webhook = os.environ.get("MONITOR_WEBHOOK_URL", "")
    if real and webhook:
        try:
            requests.post(webhook, json={"text": f"AirLens: {len(real)} peringatan monitoring", "alerts": real,
                                         "report_id": report["report_id"]}, timeout=5)
        except requests.RequestException as exc:
            logger.warning("webhook monitoring gagal: %s", type(exc).__name__)
    logger.info("monitoring selesai: %d prediksi, %d peringatan, laporan %s", report["n"], len(real), md)
    return report
