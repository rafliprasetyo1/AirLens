"""Bundle model: satu folder per model berisi model + metadata.json (kelas, temperatur, ambang, versi data/kode).

Lokasi: artifacts/models/<data_version[:12]>/<nama>/. Model CNN disimpan sebagai ONNX (inferensi API di CPU tanpa
PyTorch); baseline sebagai joblib (hanya untuk evaluasi). candidates.json mencatat semua bundle dan mana yang
dipilih sebagai production (berdasarkan macro-F1 validasi).
"""

import json
import os
from pathlib import Path

import joblib
import numpy as np

from airlens.models.preprocess import preprocess

ARTIFACTS_DIR = Path(os.environ.get("AIRLENS_ARTIFACTS_DIR", "/app/artifacts"))


def models_dir(data_version: str) -> Path:
    return ARTIFACTS_DIR / "models" / data_version[:12]


def features_cache(data_version: str) -> Path:
    return ARTIFACTS_DIR / "features" / f"{data_version[:12]}.parquet"


def save_metadata(bundle_dir: Path, meta: dict) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))


def load_metadata(bundle_dir: Path) -> dict:
    return json.loads((bundle_dir / "metadata.json").read_text())


def write_candidates(data_version: str, candidates: dict) -> Path:
    path = models_dir(data_version) / "candidates.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(candidates, indent=2, ensure_ascii=False))
    return path


def read_candidates(data_version: str) -> dict:
    path = models_dir(data_version) / "candidates.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} belum ada; jalankan `make train` untuk data_version ini")
    return json.loads(path.read_text())


def onnx_logits(model_path: Path, image_paths: list[str], batch: int = 32) -> np.ndarray:
    import onnxruntime as ort

    sess = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    out = []
    for i in range(0, len(image_paths), batch):
        x = np.concatenate([preprocess(p) for p in image_paths[i : i + batch]])
        out.append(sess.run(["logits"], {"image": x})[0])
    return np.concatenate(out) if out else np.zeros((0, 0), dtype=np.float32)


def bundle_logits(bundle_dir: Path, image_paths: list[str], features=None) -> np.ndarray:
    """Logit (atau log-probabilitas untuk baseline) bundle pada daftar gambar. Baseline butuh tabel fitur."""
    meta = load_metadata(bundle_dir)
    if meta["kind"] == "onnx":
        return onnx_logits(bundle_dir / "model.onnx", image_paths)
    from airlens.models.baseline import logits_from_proba

    model = joblib.load(bundle_dir / "model.joblib")
    return logits_from_proba(model, np.asarray(features, dtype=np.float64), len(meta["classes"]))
