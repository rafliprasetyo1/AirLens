"""Sensor Beta (ESP32 + satu MQ-2): baseline, rasio, dan status per node.

Alur per bacaan (dijalankan di server, bukan di perangkat):
1. Bacaan disimpan apa adanya. Nilai <= 0 (mis. -1 saat kabel sensor lepas) ditandai valid=False dan tidak
   dipakai menghitung baseline maupun status.
2. Pemanasan: selama `warmup_seconds` sejak bacaan pertama (atau sejak reset / perangkat restart) node berstatus
   warming_up. Setelah itu baseline = median `baseline_samples` bacaan valid pertama.
3. ratio = Rs / baseline. MQ-2: makin banyak gas/asap, Rs makin kecil, jadi ratio turun.
4. Histeresis: normal -> alert bila ratio < alert_ratio sebanyak alert_consecutive kali berturut-turut;
   alert -> normal bila ratio > recover_ratio. Di antara keduanya status tidak berubah (tidak berkedip).

Format 4 MQ (revisi Beta SHAP): bacaan berisi tegangan pin ADC (mV) MQ-2, MQ-3, MQ-7, MQ-135. Rs tiap sensor dihitung
dari mV (airlens.data.beta_gas.rs_from_mv); baseline = median Rs per sensor setelah pemanasan; fitur = Rs/R0 + MQ-3/MQ-2
(sama dengan dataset latih). Model gas Beta (production) memberi peluang 4 kelas + SHAP kelas terpilih; challenger
(bila ada) dihitung diam-diam (shadow). Status: asap (smoke/smoke_alcohol) atau alkohol dengan peluang >= enter_prob
sebanyak `consecutive` kali -> alert; keluar bila peluang clean_air >= exit_clean_prob. Tanpa model: aturan rasio MQ-2.

Logika status ditulis sebagai fungsi murni (mudah dites); penyimpanan memakai satu transaksi per bacaan dengan kunci
baris node (SELECT ... FOR UPDATE) agar dua bacaan bersamaan dari node yang sama tidak saling menimpa.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from airlens.db.models import SensorNode, SensorReading


@dataclass(frozen=True)
class SensorConfig:
    warmup_seconds: float = 180
    baseline_samples: int = 24
    alert_ratio: float = 0.6
    alert_consecutive: int = 2
    recover_ratio: float = 0.8
    offline_seconds: float = 20
    history_max_minutes: int = 120
    model_enter_prob: float = 0.70
    model_exit_clean_prob: float = 0.60
    smoke_classes: tuple[str, ...] = ("smoke", "smoke_alcohol")
    alcohol_classes: tuple[str, ...] = ()   # kosong = alkohol hanya ditampilkan, tidak memicu peringatan

    @classmethod
    def from_profile(cls, profile: dict, triggers: dict | None = None) -> "SensorConfig":
        """Pemanasan/baseline/offline dari profil; ambang alert dari config/triggers.yaml (satu sumber kebenaran)."""
        cfg = dict(profile.get("sensor", {}))
        beta = (triggers or {}).get("beta")
        if beta:
            cfg.update(alert_ratio=beta["enter_ratio"], alert_consecutive=beta["consecutive"], recover_ratio=beta["exit_ratio"])
            m = beta.get("model")
            if m:
                cfg.update(model_enter_prob=m["enter_prob"], model_exit_clean_prob=m["exit_clean_prob"],
                           smoke_classes=tuple(m["smoke_classes"]), alcohol_classes=tuple(m["alcohol_classes"]))
        return cls(**cfg)


# ------------------------------------------------------------------ logika murni
def is_valid(rs_kohm: float) -> bool:
    return rs_kohm > 0


def baseline_from(values: list[float], n: int) -> float | None:
    """Median n nilai valid pertama; None bila belum cukup."""
    return float(statistics.median(values[:n])) if len(values) >= n else None


def next_state(state: str, low_streak: int, ratio: float, cfg: SensorConfig) -> tuple[str, int]:
    """Status berikutnya dengan histeresis. Mengembalikan (status, low_streak)."""
    if state == "alert":
        return ("normal", 0) if ratio > cfg.recover_ratio else ("alert", 0)
    streak = low_streak + 1 if ratio < cfg.alert_ratio else 0
    return ("alert", 0) if streak >= cfg.alert_consecutive else ("normal", streak)


def next_state_model(state: str, streak: int, probs: dict[str, float], label: str | None,
                     cfg: SensorConfig) -> tuple[str, int, str | None]:
    """Histeresis berbasis peluang model. Mengembalikan (status, streak, label alert)."""
    p_smoke = sum(probs.get(c, 0.0) for c in cfg.smoke_classes)
    p_alcohol = sum(probs.get(c, 0.0) for c in cfg.alcohol_classes)
    candidate = ("smoke" if p_smoke >= cfg.model_enter_prob
                 else "alcohol" if cfg.alcohol_classes and p_alcohol >= cfg.model_enter_prob else None)
    if state == "alert":
        if probs.get("clean_air", 0.0) >= cfg.model_exit_clean_prob:
            return "normal", 0, None
        return "alert", 0, candidate or label
    streak = streak + 1 if candidate else 0
    return ("alert", 0, candidate) if streak >= cfg.alert_consecutive else ("normal", streak, None)


MV_FIELDS = {"MQ2": "mq2_mv", "MQ3": "mq3_mv", "MQ7": "mq7_mv", "MQ135": "mq135_mv"}
MAX_PIN_MV = 3300.0   # ADC ESP32: pin tidak boleh di atas 3,3 V (pembagi 10k/20k menjaga 5 V -> 3,33 V)


def mv_valid(mv: dict[str, float]) -> bool:
    """Semua sensor ada dan di dalam rentang pin. 0 = kabel lepas/sensor mati; >= 3300 = pembagi salah sambung."""
    return all(s in mv and mv[s] is not None and 0 < float(mv[s]) < MAX_PIN_MV for s in MV_FIELDS)


def rebooted(previous_uptime: int | None, uptime: int | None) -> bool:
    """Uptime perangkat mundur = ESP32 baru menyala lagi; pemanas MQ dingin, jadi pemanasan diulang."""
    return previous_uptime is not None and uptime is not None and uptime < previous_uptime


# ------------------------------------------------------------------ penyimpanan
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _reset(node: SensorNode, now: datetime) -> None:
    node.baseline_started_at, node.baseline_kohm, node.state, node.low_streak = now, None, "warming_up", 0
    node.baseline_rs, node.alert_label = None, None


def record_reading(engine: Engine, cfg: SensorConfig, node_id: str, rs_kohm: float | None, uptime_s: int | None,
                   simulated: bool, now: datetime | None = None, mv: dict[str, float] | None = None,
                   model=None, challenger=None) -> dict:
    """Satu bacaan. Format lama: rs_kohm. Format 4 MQ: mv = {"MQ2": mV, ...} (+ model/challenger BetaModelStore)."""
    if mv is not None:
        return _record_mv(engine, cfg, node_id, mv, uptime_s, simulated, now or _now(), model, challenger)
    now = now or _now()
    valid = is_valid(rs_kohm)
    with Session(engine) as s, s.begin():
        s.execute(insert(SensorNode).values(node_id=node_id, baseline_started_at=now, state="warming_up",
                                            low_streak=0).on_conflict_do_nothing(index_elements=["node_id"]))
        node = s.get(SensorNode, node_id, with_for_update=True)
        if rebooted(node.last_uptime_s, uptime_s):
            _reset(node, now)
        if uptime_s is not None:
            node.last_uptime_s = uptime_s
        ratio = None
        if valid:
            if node.baseline_kohm is None:
                warm_end = node.baseline_started_at + timedelta(seconds=cfg.warmup_seconds)
                if now >= warm_end:
                    earlier = s.scalars(
                        select(SensorReading.mq2_rs_kohm)
                        .where(SensorReading.node_id == node_id, SensorReading.valid.is_(True),
                               SensorReading.received_at >= warm_end)
                        .order_by(SensorReading.received_at, SensorReading.id)
                        .limit(cfg.baseline_samples)).all()
                    baseline = baseline_from([*earlier, rs_kohm], cfg.baseline_samples)
                    if baseline is not None:
                        node.baseline_kohm, node.state, node.low_streak = baseline, "normal", 0
            if node.baseline_kohm is not None:
                ratio = rs_kohm / node.baseline_kohm
                node.state, node.low_streak = next_state(node.state, node.low_streak, ratio, cfg)
        node.updated_at = now
        s.add(SensorReading(node_id=node_id, received_at=now, mq2_rs_kohm=rs_kohm, uptime_s=uptime_s,
                            ratio=ratio, state=node.state, valid=valid, simulated=simulated))
        return {"accepted": True, "node_id": node_id, "valid": valid, "state": node.state,
                "ratio": round(ratio, 4) if ratio is not None else None}


def _record_mv(engine: Engine, cfg: SensorConfig, node_id: str, mv: dict[str, float], uptime_s: int | None,
               simulated: bool, now: datetime, model, challenger) -> dict:
    from airlens.data.beta_gas import device_features, rs_from_mv

    bcfg = _beta_cfg()
    valid = mv_valid(mv)
    rs = {s: rs_from_mv(mv[s]) for s in MV_FIELDS} if valid else None
    out = {"model_available": False, "class": None, "probs": None, "reason": None, "label": None, "features": None}
    row = {}
    with Session(engine) as s, s.begin():
        s.execute(insert(SensorNode).values(node_id=node_id, baseline_started_at=now, state="warming_up",
                                            low_streak=0).on_conflict_do_nothing(index_elements=["node_id"]))
        node = s.get(SensorNode, node_id, with_for_update=True)
        if rebooted(node.last_uptime_s, uptime_s):
            _reset(node, now)
        if uptime_s is not None:
            node.last_uptime_s = uptime_s
        ratio = None
        if valid:
            if node.baseline_rs is None:
                warm_end = node.baseline_started_at + timedelta(seconds=cfg.warmup_seconds)
                if now >= warm_end:
                    earlier = s.execute(
                        select(*[getattr(SensorReading, c) for c in MV_FIELDS.values()])
                        .where(SensorReading.node_id == node_id, SensorReading.valid.is_(True),
                               SensorReading.mq2_mv.is_not(None), SensorReading.received_at >= warm_end)
                        .order_by(SensorReading.received_at, SensorReading.id)
                        .limit(cfg.baseline_samples)).all()
                    rows = [dict(zip(MV_FIELDS, r)) for r in earlier] + [mv]
                    if len(rows) >= cfg.baseline_samples:
                        rows = rows[:cfg.baseline_samples]
                        node.baseline_rs = {k: float(statistics.median(rs_from_mv(r[k]) for r in rows)) for k in MV_FIELDS}
                        node.baseline_kohm = node.baseline_rs["MQ2"]
                        node.state, node.low_streak, node.alert_label = "normal", 0, None
            if node.baseline_rs is not None:
                feats = device_features(mv, node.baseline_rs, bcfg)
                ratio = feats["r_mq2"]
                out["features"] = {k: round(v, 4) for k, v in feats.items()}
                pred = _safe_predict(model, feats)
                if pred is not None:
                    out.update(model_available=True, **{k: pred[k] for k in ("class", "probs", "reason")})
                    node.state, node.low_streak, node.alert_label = next_state_model(
                        node.state, node.low_streak, pred["probs"], node.alert_label, cfg)
                    row.update(predicted_class=pred["class"], probs=pred["probs"], shap=pred["shap"],
                               reason=pred["reason"], model_version=pred["model_version"])
                else:   # model belum ada: aturan rasio MQ-2 (perilaku Beta lama)
                    node.state, node.low_streak = next_state(node.state, node.low_streak, ratio, cfg)
                    node.alert_label = None
                shadow = _safe_predict(challenger, feats)
                if shadow is not None:
                    row["challenger_class"] = shadow["class"]
                row["features"] = feats
        node.updated_at = now
        s.add(SensorReading(node_id=node_id, received_at=now, mq2_rs_kohm=rs["MQ2"] if rs else None, uptime_s=uptime_s,
                            ratio=ratio, state=node.state, valid=valid, simulated=simulated,
                            **{c: (float(mv[k]) if mv.get(k) is not None else None) for k, c in MV_FIELDS.items()}, **row))
        out.update(accepted=True, node_id=node_id, valid=valid, state=node.state,
                   ratio=round(ratio, 4) if ratio is not None else None,
                   label=node.alert_label if node.state == "alert" else None)
        return out


def _safe_predict(store, feats: dict) -> dict | None:
    if store is None or getattr(store, "status", None) != "ok":
        return None
    try:
        return store.predict(feats)
    except Exception:   # model berganti/rusak di tengah jalan: bacaan tetap disimpan dengan aturan cadangan
        return None


_BETA_CFG: dict | None = None


def _beta_cfg() -> dict:
    global _BETA_CFG
    if _BETA_CFG is None:
        from airlens.data.beta_gas import load_beta_config

        _BETA_CFG = load_beta_config()
    return _BETA_CFG


def reset_baseline(engine: Engine, node_id: str, now: datetime | None = None) -> bool:
    with Session(engine) as s, s.begin():
        node = s.get(SensorNode, node_id, with_for_update=True)
        if node is None:
            return False
        _reset(node, now or _now())
        return True


def latest(engine: Engine, cfg: SensorConfig, node_id: str, now: datetime | None = None) -> dict | None:
    now = now or _now()
    with Session(engine) as s:
        node = s.get(SensorNode, node_id)
        if node is None:
            return None
        last = s.scalars(select(SensorReading).where(SensorReading.node_id == node_id)
                         .order_by(SensorReading.received_at.desc(), SensorReading.id.desc()).limit(1)).first()
        warm_end = node.baseline_started_at + timedelta(seconds=cfg.warmup_seconds)
        samples = 0
        if node.baseline_kohm is None:
            samples = len(s.scalars(select(SensorReading.id).where(
                SensorReading.node_id == node_id, SensorReading.valid.is_(True),
                SensorReading.received_at >= warm_end).limit(cfg.baseline_samples)).all())
    age = (now - last.received_at).total_seconds() if last else None
    return {
        "node_id": node_id,
        "state": node.state,
        "online": age is not None and age <= cfg.offline_seconds,
        "seconds_since": round(age, 1) if age is not None else None,
        "received_at": last.received_at.isoformat() if last else None,
        "rs_kohm": last.mq2_rs_kohm if last else None,
        "ratio": round(last.ratio, 4) if last and last.ratio is not None else None,
        "valid": last.valid if last else None,
        "simulated": last.simulated if last else False,
        "baseline_kohm": round(node.baseline_kohm, 3) if node.baseline_kohm is not None else None,
        "thresholds": {"alert": cfg.alert_ratio, "recover": cfg.recover_ratio},
        "format": "mq4" if last is not None and last.mq2_mv is not None else "mq2",
        "sensors": None if last is None or last.mq2_mv is None else {
            "mv": {k: getattr(last, c) for k, c in MV_FIELDS.items()},
            "ratios": {k: (last.features or {}).get(f"r_{k.lower()}") for k in MV_FIELDS},
            "baseline_rs_kohm": {k: round(v, 3) for k, v in (node.baseline_rs or {}).items()} or None},
        "model": None if last is None or last.mq2_mv is None else {
            "available": last.predicted_class is not None, "class": last.predicted_class, "probs": last.probs,
            "reason": last.reason, "version": last.model_version, "alert_label": node.alert_label},
        "warmup": None if node.baseline_kohm is not None else {
            "remaining_s": max(0.0, round((warm_end - now).total_seconds(), 1)),
            "samples": samples, "needed": cfg.baseline_samples},
    }


def history(engine: Engine, cfg: SensorConfig, node_id: str, minutes: int, now: datetime | None = None,
            since: datetime | None = None) -> list[dict]:
    """Bacaan `minutes` terakhir; `since` = hanya yang lebih baru (halaman cukup mengambil tambahan, hemat kuota ngrok)."""
    now = now or _now()
    minutes = max(1, min(int(minutes), cfg.history_max_minutes))
    with Session(engine) as s:
        rows = s.execute(select(SensorReading.received_at, SensorReading.mq2_rs_kohm, SensorReading.ratio,
                                SensorReading.state, SensorReading.valid, SensorReading.features,
                                SensorReading.predicted_class)
                         .where(SensorReading.node_id == node_id,
                                SensorReading.received_at >= max(now - timedelta(minutes=minutes), since or datetime.min.replace(tzinfo=timezone.utc)),
                                SensorReading.received_at > (since or datetime.min.replace(tzinfo=timezone.utc)))
                         .order_by(SensorReading.received_at, SensorReading.id)).all()
    return [{"t": r.received_at.isoformat(), "rs_kohm": r.mq2_rs_kohm,
             "ratio": round(r.ratio, 4) if r.ratio is not None else None, "state": r.state, "valid": r.valid,
             "ratios": {k: round(v, 4) for k, v in r.features.items() if k.startswith("r_")} if r.features else None,
             "class": r.predicted_class}
            for r in rows]


def explain_latest(engine: Engine, node_id: str) -> dict | None:
    """SHAP bacaan terbaru: fitur, nilai dasar, SHAP per fitur kelas terpilih, skor akhir, kalimat alasan.
    None bila node belum pernah mengirim data."""
    with Session(engine) as s:
        last = s.scalars(select(SensorReading).where(SensorReading.node_id == node_id)
                         .order_by(SensorReading.received_at.desc(), SensorReading.id.desc()).limit(1)).first()
    if last is None:
        return None
    base = {"node_id": node_id, "received_at": last.received_at.isoformat(), "simulated": last.simulated,
            "state": last.state, "features": last.features}
    if last.shap is None:
        reason = ("model not available" if last.features else
                  "warming up: no explanation until the clean-air baseline is learned" if last.mq2_mv is not None
                  else "this node sends the old single-sensor format (MQ-2 only)")
        return {**base, "model_available": False, "detail": reason}
    sh = last.shap
    return {**base, "model_available": True, "class": last.predicted_class, "probs": last.probs,
            "expected_value": sh["base"], "shap": sh["values"], "score": sh["score"], "reason": last.reason,
            "model_version": last.model_version}


def nodes(engine: Engine, cfg: SensorConfig, now: datetime | None = None) -> list[dict]:
    """Semua node, terbaru dulu: dipakai halaman Beta untuk memilih node (alat asli diutamakan bila online)."""
    now = now or _now()
    with Session(engine) as s:
        rows = s.scalars(select(SensorNode).order_by(SensorNode.updated_at.desc())).all()
        out = []
        for n in rows:
            sim = s.scalars(select(SensorReading.simulated).where(SensorReading.node_id == n.node_id)
                            .order_by(SensorReading.received_at.desc(), SensorReading.id.desc()).limit(1)).first()
            age = (now - n.updated_at).total_seconds()
            out.append({"node_id": n.node_id, "state": n.state, "simulated": bool(sim),
                        "online": age <= cfg.offline_seconds, "seconds_since": round(age, 1)})
    return out
