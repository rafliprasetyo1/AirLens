"""Alur utama satu prediksi (CLAUDE.md, ALUR UTAMA langkah 2-7). Setiap tahap mengirim event NYATA ke job.

Tahap: periksa (validasi + hapus EXIF + cek foto luar ruangan/siang/langit) -> analisis (praproses, model,
kalibrasi, ambang, petunjuk visual) -> iqair (pembanding) -> selesai. Hasil selalu dicatat ke db, termasuk foto
yang ditolak dan galat model.
"""

import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.special import softmax
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from airlens.aqi import BREAKPOINTS, CATEGORY_LABELS, aqi_to_category
from airlens.data.quality import image_stats, reject_reason
from airlens.monitoring.signature import input_signature, project
from airlens.db.models import Prediction
from airlens.features.haze import HINTS, haze_features, hint_values
from airlens.models.preprocess import to_array
from airlens_api.iqair import IQAirClient, IQAirUnavailable, Reading
from airlens_api.jobs import Job, JobStore
from airlens_api.model_store import ModelStore, ModelUnavailable
from airlens_api.validation import UploadRejected, validate_and_strip

logger = logging.getLogger("airlens.api.pipeline")

DISCLAIMER = "Perkiraan dari foto, bukan pengukuran resmi."
# Warna resmi AQI US EPA; teks di atasnya dipilih agar kontras >= 4,5:1.
COLORS = {
    "good": ("#00E400", "#0b0b0b"), "moderate": ("#FFFF00", "#0b0b0b"), "usg": ("#FF7E00", "#0b0b0b"),
    "unhealthy": ("#FF0000", "#0b0b0b"), "very_unhealthy": ("#8F3F97", "#ffffff"), "hazardous": ("#7E0023", "#ffffff"),
}
ADVICE = {
    "good": "Kualitas udara baik. Aman untuk beraktivitas di luar ruangan.",
    "moderate": "Umumnya aman. Orang yang sangat sensitif sebaiknya mengurangi aktivitas berat yang lama di luar.",
    "usg": "Anak, lansia, dan penderita asma atau penyakit jantung sebaiknya mengurangi aktivitas berat di luar.",
    "unhealthy": "Semua orang sebaiknya mengurangi aktivitas berat di luar ruangan; kelompok sensitif menghindarinya.",
    "very_unhealthy": "Hindari aktivitas di luar ruangan. Bila harus keluar, gunakan masker yang sesuai (mis. N95).",
    "hazardous": "Tetap di dalam ruangan dan tutup jendela. Ikuti arahan resmi pemerintah setempat.",
}
REJECT_MESSAGES = {
    "terlalu_kecil": "Foto terlalu kecil. Gunakan foto minimal 100 piksel di sisi terpendek.",
    "terlalu_gelap": "Foto terlalu gelap atau diambil malam hari. Gunakan foto siang hari.",
    "terlalu_terang": "Foto terlalu terang (overexposed). Coba foto lain.",
    "langit_tidak_terlihat": "Langit tidak terlihat. Gunakan foto luar ruangan dengan langit di bagian atas.",
}


@dataclass
class Request:
    data: bytes
    city: dict | None  # {"city","state","country"}
    coords: tuple[float, float] | None
    store_photo: bool


def class_ranges(classes: list[str], class_merge: dict[str, str]) -> dict[str, tuple[int, int]]:
    """Rentang indeks AQI tiap kelas akhir (kelas gabungan mencakup rentang semua kelas asalnya)."""
    base = {row[4]: (row[2], row[3]) for row in BREAKPOINTS[2024]}
    out: dict[str, list[int]] = {}
    for orig, (lo, hi) in base.items():
        tgt = class_merge.get(orig, orig)
        cur = out.setdefault(tgt, [lo, hi])
        cur[0], cur[1] = min(cur[0], lo), max(cur[1], hi)
    return {c: tuple(out[c]) for c in classes}


def percentile_of(value: float, quantiles: list[float]) -> float:
    """Posisi persentil (0-100) nilai terhadap kuantil data latih (kuantil 0,5,...,100)."""
    return float(np.interp(value, quantiles, np.linspace(0, 100, len(quantiles))))


class PredictionPipeline:
    def __init__(self, models: ModelStore, iqair: IQAirClient, jobs: JobStore, engine: Engine, cfg: dict,
                 uploads_dir: Path, challenger: ModelStore | None = None):
        self.models, self.iqair, self.jobs, self.engine, self.cfg = models, iqair, jobs, engine, cfg
        self.challenger = challenger
        self.uploads_dir = uploads_dir
        self.max_bytes = cfg["api"]["max_upload_mb"] * 2**20
        self.class_merge = cfg["data"]["class_merge"]

    # ------------------------------------------------------------------ util
    def _category_view(self, cat: str, classes: list[str]) -> dict:
        lo, hi = class_ranges(classes, self.class_merge)[cat]
        merged_from = [c for c, t in self.class_merge.items() if t == cat]
        label = " / ".join([CATEGORY_LABELS[cat], *(CATEGORY_LABELS[c] for c in merged_from)])
        bg, fg = COLORS[cat]
        return {"key": cat, "label": label, "aqi_range": [lo, hi], "color": bg,
                "text_color": fg, "advice": ADVICE[cat]}

    def _iqair_view(self, reading: Reading, pred_cat: str | None, classes: list[str]) -> dict:
        cat = self.class_merge.get(aqi_to_category(reading.aqi_us), aqi_to_category(reading.aqi_us))
        view = {"status": "ok", "aqi_us": reading.aqi_us, "city": reading.city, "state": reading.state,
                "country": reading.country, "main_pollutant": reading.main_pollutant,
                "observed_at": reading.observed_at.isoformat() if reading.observed_at else None,
                "cached": reading.cached, "category": self._category_view(cat, classes)}
        if pred_cat:
            lo, hi = class_ranges(classes, self.class_merge)[pred_cat]
            view["selisih_kategori"] = classes.index(pred_cat) - classes.index(cat)
            view["jarak_ke_rentang"] = 0 if lo <= reading.aqi_us <= hi else (
                lo - reading.aqi_us if reading.aqi_us < lo else reading.aqi_us - hi)
        return view

    def _shadow(self, job: Job, x, input_stats: dict, sha: str, reading, base_log: dict) -> None:
        """Shadow mode: challenger memprediksi foto yang sama dan DICATAT saja (is_shadow), tidak ditampilkan.

        Galat apa pun di challenger hanya dicatat di log dan tidak pernah memengaruhi respons pengguna.
        """
        ch = self.challenger
        if ch is None or ch.status != "ok":
            return
        try:
            start = time.perf_counter()
            logits, _ = ch.infer(x)
            meta = ch.meta
            probs = softmax(logits[0] / meta["temperature"])
            k = int(probs.argmax())
            uncertain = float(probs[k]) < float(meta["threshold"]["threshold"])
            self._log(job, status="uncertain" if uncertain else "ok", predicted_class=meta["classes"][k],
                      confidence=float(probs[k]), probabilities={c: round(float(p), 5) for c, p in zip(meta["classes"], probs)},
                      image_sha256=sha, input_stats=input_stats, iqair_aqi_us=reading.aqi_us if reading else None,
                      latency_ms=(time.perf_counter() - start) * 1000, is_shadow=True,
                      **{**base_log, "model_version": ch.version, "data_version": meta.get("data_version")})
        except Exception:
            logger.exception("shadow (challenger %s) gagal; diabaikan", ch.version)

    def _log(self, job: Job, **fields) -> None:
        with Session(self.engine) as s:
            s.add(Prediction(job_id=job.id, **fields))
            s.commit()

    # ------------------------------------------------------------------ alur
    def run(self, job: Job, req: Request) -> None:
        start = time.perf_counter()
        model_info = self.models.info()
        base_log = {"model_version": model_info["version"] or "tidak-tersedia", "data_version": model_info["data_version"],
                    "city": (req.city or {}).get("city")}
        try:
            self._run(job, req, start, base_log)
        except Exception:  # galat tak terduga: tetap beri tahu pengguna dan catat
            logger.exception("job %s gagal", job.id)
            self.jobs.emit(job, "galat", "gagal", message="Terjadi galat di server.")
            self.jobs.finish(job, {"status": "error", "code": "galat_server", "message": "Terjadi galat di server. Coba lagi.",
                                   "disclaimer": DISCLAIMER})
            self._log(job, status="rejected", reject_reason="galat_server",
                      latency_ms=(time.perf_counter() - start) * 1000, **base_log)

    def _run(self, job: Job, req: Request, start: float, base_log: dict) -> None:
        # ---------------- 1. periksa
        self.jobs.emit(job, "periksa", "mulai")
        try:
            img, fmt = validate_and_strip(req.data, self.max_bytes)
        except UploadRejected as e:
            self.jobs.emit(job, "periksa", "gagal", code=e.code, message=e.message)
            self.jobs.finish(job, {"status": "rejected", "code": e.code, "message": e.message, "disclaimer": DISCLAIMER})
            self._log(job, status="rejected", reject_reason=e.code, latency_ms=(time.perf_counter() - start) * 1000,
                      **base_log)
            return
        stats = image_stats(img)
        reason = reject_reason(stats)
        sha = hashlib.sha256(img.tobytes()).hexdigest()  # hash piksel (tanpa metadata)
        input_stats = {"width": stats.width, "height": stats.height, "format": fmt,
                       **{k: round(v, 5) for k, v in input_signature(img).items()}}  # fitur drift, sama dgn trainer
        if reason:
            msg = REJECT_MESSAGES[reason]
            self.jobs.emit(job, "periksa", "gagal", code=reason, message=msg)
            self.jobs.finish(job, {"status": "rejected", "code": reason, "message": msg, "disclaimer": DISCLAIMER})
            self._log(job, status="rejected", reject_reason=reason, image_sha256=sha, input_stats=input_stats,
                      latency_ms=(time.perf_counter() - start) * 1000, **base_log)
            return
        self.jobs.emit(job, "periksa", "selesai")

        # ---------------- 2. analisis
        self.jobs.emit(job, "analisis", "mulai")
        x = to_array(img)[None]
        try:
            logits, emb = self.models.infer(x)
        except ModelUnavailable as e:
            msg = "Model belum tersedia. Coba lagi beberapa saat lagi."
            self.jobs.emit(job, "analisis", "gagal", code="model_tidak_tersedia", message=msg)
            self.jobs.finish(job, {"status": "error", "code": "model_tidak_tersedia", "message": msg, "detail": str(e)[:200],
                                   "disclaimer": DISCLAIMER})
            self._log(job, status="rejected", reject_reason="model_tidak_tersedia", image_sha256=sha,
                      input_stats=input_stats, latency_ms=(time.perf_counter() - start) * 1000, **base_log)
            return
        meta = self.models.meta
        classes = meta["classes"]
        pca = (meta.get("monitoring_reference") or {}).get("emb_pca")
        if emb is not None and pca:
            input_stats["emb_pca"] = project(emb[0], pca)[0].round(4).tolist()
        probs = softmax(logits[0] / meta["temperature"])
        k = int(probs.argmax())
        threshold = float(meta["threshold"]["threshold"])
        uncertain = float(probs[k]) < threshold
        pred_cat = classes[k]
        feats = haze_features(img)
        hints_raw = hint_values(feats)
        ref = meta.get("hint_reference", {})
        hints = [{"key": h, "label": HINTS[h]["label"], "value": round(v, 4), "hazier": HINTS[h]["hazier"],
                  "percentile": round(percentile_of(v, ref[h]), 1) if h in ref else None}
                 for h, v in hints_raw.items()]
        self.jobs.emit(job, "analisis", "selesai")

        # ---------------- 3. pembanding IQAir
        self.jobs.emit(job, "iqair", "mulai")
        reading, iq_view = None, None
        try:
            if req.coords:
                reading = self.iqair.by_coords(*req.coords)
            elif req.city:
                reading = self.iqair.by_city(req.city["city"], req.city["state"], req.city["country"])
            else:
                raise IQAirUnavailable("tanpa_lokasi", "Pilih kota atau izinkan lokasi untuk pembanding IQAir.")
            iq_view = self._iqair_view(reading, None if uncertain else pred_cat, classes)
            self.jobs.emit(job, "iqair", "selesai")
        except IQAirUnavailable as e:
            iq_view = {"status": "tidak_tersedia", "code": e.code, "message": e.message}
            self.jobs.emit(job, "iqair", "gagal", code=e.code, message=e.message)

        # ---------------- 4. simpan foto (hanya dengan persetujuan) + catat
        photo_stored = False
        if req.store_photo:
            self.uploads_dir.mkdir(parents=True, exist_ok=True)
            img.save(self.uploads_dir / f"{sha}.jpg", format="JPEG", quality=92)  # tanpa EXIF (gambar hasil salinan)
            photo_stored = True
        latency = (time.perf_counter() - start) * 1000
        status = "uncertain" if uncertain else "ok"
        self._log(job, status=status, predicted_class=pred_cat, confidence=float(probs[k]),
                  probabilities={c: round(float(p), 5) for c, p in zip(classes, probs)}, image_sha256=sha,
                  input_stats=input_stats, iqair_aqi_us=reading.aqi_us if reading else None,
                  iqair_reading_id=reading.id if reading else None, latency_ms=latency, photo_stored=photo_stored,
                  **base_log)
        self._shadow(job, x, input_stats, sha, reading, base_log)
        self.jobs.finish(job, {
            "status": status,
            "category": None if uncertain else self._category_view(pred_cat, classes),
            "top_candidate": self._category_view(pred_cat, classes),
            "confidence": round(float(probs[k]), 4),
            "threshold": round(threshold, 4),
            "probabilities": [{"key": c, "label": CATEGORY_LABELS[c], "p": round(float(p), 4)}
                              for c, p in zip(classes, probs)],
            "hints": hints,
            "iqair": iq_view,
            "model": {"version": self.models.version, "name": meta.get("name"), "data_version": meta.get("data_version"),
                      "smoke": meta.get("smoke", False)},
            "photo_stored": photo_stored,
            "latency_ms": round(latency, 1),
            "disclaimer": DISCLAIMER,
        })
