"""Model gas Beta (`airlens-beta-gas`, LightGBM) di API: prediksi per bacaan + TreeSHAP persis + kalimat alasan.

Memakai pola ModelStore yang sama (alias production/challenger dari MLflow, cache per versi, cadangan cache saat
MLflow mati, muat ulang otomatis saat alias pindah). Bedanya hanya isi bundle: model LightGBM (`model.lgb` dari flavor
MLflow, atau `model.txt` di bundle lokal) + metadata.json. SHAP dihitung LightGBM sendiri (`pred_contrib=True`):
nilai dasar + jumlah SHAP = skor mentah kelas (log-odds softmax), sehingga pustaka shap tidak perlu dimuat di API.
BETA_BUNDLE_DIR / BETA_CHALLENGER_BUNDLE_DIR (opsional) = bundle lokal tanpa MLflow (dipakai tes).
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

import numpy as np

from airlens_api.model_store import ModelStore, ModelUnavailable

logger = logging.getLogger("airlens.api.beta_model")
MODEL_NAME = "airlens-beta-gas"
LOCAL_ENV = {"production": "BETA_BUNDLE_DIR", "challenger": "BETA_CHALLENGER_BUNDLE_DIR"}
TITLES = {"smoke": "Smoke likely", "smoke_alcohol": "Smoke and alcohol likely", "alcohol": "Alcohol/VOC likely",
          "clean_air": "Clean air"}


def pretty_name(feature: str) -> str:
    if feature == "mq3_over_mq2":
        return "MQ-3 / MQ-2"
    return "MQ-" + feature[len("r_mq"):] if feature.startswith("r_mq") else feature


def reason_sentence(cls: str, features: dict[str, float], shap_values: dict[str, float], top: int = 3) -> str:
    """'Smoke likely: MQ-135 at 0.64× clean air (+1.92), MQ-7 at 0.93× (+0.41).' — fitur yang paling mendorong ke
    kelas terpilih (SHAP positif terbesar), paling banyak `top`. Rasio = Rs terhadap udara bersih (turun saat gas)."""
    pushing = sorted(((v, f) for f, v in shap_values.items() if v > 0), reverse=True)[:top]
    if not pushing:
        return f"{TITLES.get(cls, cls)}."
    parts = []
    for i, (v, f) in enumerate(pushing):
        if f == "mq3_over_mq2":
            parts.append(f"{pretty_name(f)} at {features[f]:.2f} (+{v:.2f})")
        else:
            parts.append(f"{pretty_name(f)} at {features[f]:.2f}×{' clean air' if i == 0 else ''} (+{v:.2f})")
    return f"{TITLES.get(cls, cls)}: " + ", ".join(parts) + "."


class BetaModelStore(ModelStore):
    def __init__(self, cache_dir: Path, alias: str = "production", retry_seconds: float = 30.0):
        super().__init__(cache_dir, alias, retry_seconds, model=MODEL_NAME, local_env=LOCAL_ENV.get(alias, ""))
        self._booster = None
        self._bundle: Path | None = None
        self._plot_lock = threading.Lock()

    # ModelStore memuat ONNX; di sini isinya LightGBM.
    def _from_dir(self, bundle: Path, version: str) -> None:
        import lightgbm as lgb

        files = sorted(bundle.rglob("model.lgb")) + sorted(bundle.rglob("model.txt"))
        if not files or not (bundle / "metadata.json").exists():
            raise ModelUnavailable(f"bundle {bundle} tidak lengkap")
        booster = lgb.Booster(model_file=str(files[0]))
        meta = json.loads((bundle / "metadata.json").read_text())
        if booster.num_feature() != len(meta["features"]):
            raise ModelUnavailable("jumlah fitur model tidak sama dengan metadata")
        with self._lock:
            self._booster, self.meta, self.version, self._bundle = booster, meta, version, bundle
            self.status, self.error = "ok", None
        logger.info("model %s/%s aktif: versi %s (%s)", self.model, self.alias, version, meta.get("data_version", "")[:12])

    def _deactivate(self, status: str, reason: str | None) -> None:
        super()._deactivate(status, reason)
        with self._lock:
            self._booster, self._bundle = None, None

    def predict(self, features: dict[str, float]) -> dict:
        """Peluang tiap kelas, kelas terpilih, nilai dasar + SHAP kelas terpilih, kalimat alasan."""
        with self._lock:
            booster, meta, version = self._booster, self.meta, self.version
        if booster is None or meta is None:
            raise ModelUnavailable(self.error or "model Beta belum dimuat")
        names, classes = meta["features"], meta["classes"]
        x = np.array([[float(features[f]) for f in names]])
        raw = booster.predict(x, raw_score=True)[0]
        e = np.exp(raw - raw.max())
        probs = e / e.sum()
        k = int(probs.argmax())
        contrib = np.asarray(booster.predict(x, pred_contrib=True)).reshape(len(classes), len(names) + 1)
        shap_k = {f: float(v) for f, v in zip(names, contrib[k, :-1])}
        cls = classes[k]
        return {"class": cls, "probs": {c: float(p) for c, p in zip(classes, probs)},
                "shap": {"class": cls, "base": float(contrib[k, -1]), "values": shap_k, "score": float(raw[k])},
                "features": {f: float(features[f]) for f in names}, "reason": reason_sentence(cls, features, shap_k),
                "model_version": version}

    def plot_path(self, name: str) -> Path | None:
        """Plot SHAP global versi aktif: dari bundle lokal, atau diunduh sekali dari artefak run MLflow (plots/)."""
        with self._lock:
            bundle, meta = self._bundle, self.meta
        if bundle is None or meta is None:
            return None
        local = bundle / "plots" / name
        if local.exists():
            return local
        cached = bundle / "global_plots" / name
        if cached.exists():
            return cached
        run_id = meta.get("mlflow_run_id")
        if not run_id or self._local:
            return None
        with self._plot_lock:
            try:
                import mlflow

                got = Path(mlflow.artifacts.download_artifacts(run_id=run_id, artifact_path=f"plots/{name}",
                                                               dst_path=str(bundle / "global_plots.tmp")))
                cached.parent.mkdir(exist_ok=True)
                got.rename(cached)
                return cached
            except Exception as exc:  # MLflow mati: halaman cukup tanpa gambar
                logger.info("plot %s tidak tersedia: %s", name, type(exc).__name__)
                return None
            finally:
                import shutil

                shutil.rmtree(bundle / "global_plots.tmp", ignore_errors=True)

    def summary(self) -> dict:
        """Ringkasan untuk halaman Beta ("How the model decides"): metrik test, sumber data, sitasi."""
        info = self.info()
        meta = self.meta or {}
        test = meta.get("test_metrics") or {}
        return {**info, "classes": meta.get("classes"), "features": meta.get("features"),
                "test_macro_f1": test.get("macro_f1"), "test_f1": test.get("f1"),
                "baseline_rule_test_macro_f1": (meta.get("baseline_rule_test_metrics") or {}).get("macro_f1"),
                "citation": meta.get("dataset_citation")}
