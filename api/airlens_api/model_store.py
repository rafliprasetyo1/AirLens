"""Memuat model ONNX + metadata dari MLflow registry berdasarkan alias (`production` atau `challenger`).

- Unduhan disimpan di cache (volume) per versi registry, sehingga API tetap bisa memakai versi terakhir yang berhasil
  diunduh bila MLflow sedang mati (khusus production).
- Production tidak tersedia -> status "unavailable" beserta alasannya; API tetap hidup dan mencoba ulang berkala.
- Challenger tidak ada -> status "absent" (keadaan normal: tidak ada shadow mode).
- Alias diperiksa berkala; bila berpindah versi (promote/rollback/retrain) model dimuat ulang otomatis.
- MODEL_BUNDLE_DIR / CHALLENGER_BUNDLE_DIR (opsional) memuat bundle lokal tanpa MLflow (dipakai test).
"""

import json
import logging
import os
import threading
from pathlib import Path

import numpy as np

logger = logging.getLogger("airlens.api.model")
REGISTERED_MODEL = "airlens-aqi"
LOCAL_ENV = {"production": "MODEL_BUNDLE_DIR", "challenger": "CHALLENGER_BUNDLE_DIR"}


class ModelUnavailable(Exception):
    pass


class AliasMissing(Exception):
    pass


class ModelStore:
    def __init__(self, cache_dir: Path, alias: str = "production", retry_seconds: float = 30.0):
        self.cache_dir, self.alias, self.retry_seconds = cache_dir, alias, retry_seconds
        self.status = "loading"
        self.error: str | None = None
        self.meta: dict | None = None
        self.version: str | None = None
        self._session = None
        self._outputs: list[str] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()

    @property
    def _local(self) -> str | None:
        return os.environ.get(LOCAL_ENV.get(self.alias, ""), "") or None

    # ------------------------------------------------------------------ pemuatan
    def _activate(self, onnx_path: Path, meta: dict, version: str) -> None:
        import onnxruntime as ort

        session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        with self._lock:
            self._session, self.meta, self.version = session, meta, version
            self._outputs = [o.name for o in session.get_outputs()]
            self.status, self.error = "ok", None
        logger.info("model %s aktif: %s versi %s (%s)", self.alias, meta.get("name"), version,
                    meta.get("data_version", "")[:12])

    def _deactivate(self, status: str, reason: str | None) -> None:
        with self._lock:
            self._session, self.meta, self.version, self._outputs = None, None, None, []
            self.status, self.error = status, reason

    def _from_dir(self, bundle: Path, version: str) -> None:
        onnx_files = sorted(bundle.rglob("*.onnx"))
        if not onnx_files or not (bundle / "metadata.json").exists():
            raise ModelUnavailable(f"bundle {bundle} tidak lengkap")
        self._activate(onnx_files[0], json.loads((bundle / "metadata.json").read_text()), version)

    def _registry_version(self) -> tuple[str, str]:
        from mlflow import MlflowClient
        from mlflow.exceptions import MlflowException

        try:
            mv = MlflowClient().get_model_version_by_alias(REGISTERED_MODEL, self.alias)
        except MlflowException as exc:
            if "RESOURCE_DOES_NOT_EXIST" in str(getattr(exc, "error_code", "")) or "not found" in str(exc).lower():
                raise AliasMissing(f"alias {self.alias} belum ada") from None
            raise
        return mv.version, mv.run_id

    def _from_mlflow(self) -> None:
        import mlflow

        version, run_id = self._registry_version()
        dest = self.cache_dir / f"v{version}"
        if not (dest / "metadata.json").exists():
            tmp = self.cache_dir / f"v{version}.{self.alias}.tmp"
            tmp.mkdir(parents=True, exist_ok=True)
            mlflow.artifacts.download_artifacts(artifact_uri=f"models:/{REGISTERED_MODEL}/{version}",
                                                dst_path=str(tmp / "model"))
            meta_path = Path(mlflow.artifacts.download_artifacts(run_id=run_id, artifact_path="bundle/metadata.json",
                                                                 dst_path=str(tmp / "meta")))
            meta_path.rename(tmp / "metadata.json")  # pakai path yang dikembalikan MLflow, bukan menebak strukturnya
            if dest.exists():  # diunduh bersamaan oleh store lain
                import shutil

                shutil.rmtree(tmp, ignore_errors=True)
            else:
                tmp.rename(dest)
        self._from_dir(dest, f"{REGISTERED_MODEL}/{version}")

    def _latest_cached(self) -> tuple[Path, str] | None:
        versions = sorted((p for p in self.cache_dir.glob("v*") if p.is_dir() and p.name[1:].isdigit()),
                          key=lambda p: int(p.name[1:]))
        return (versions[-1], f"{REGISTERED_MODEL}/{versions[-1].name[1:]} (cache)") if versions else None

    def load(self) -> None:
        try:
            if self._local:
                self._from_dir(Path(self._local), f"lokal:{Path(self._local).name}")
            else:
                self._from_mlflow()
            return
        except AliasMissing as exc:
            reason = str(exc)
            if self.alias == "challenger":
                if self.status != "absent":
                    logger.info("tidak ada challenger: shadow mode nonaktif")
                self._deactivate("absent", None)
                return
        except Exception as exc:  # MLflow mati, file rusak: model tidak tersedia
            reason = f"{type(exc).__name__}: {exc}"[:300]
            if self.alias == "challenger":  # challenger tidak boleh mengganggu: cukup nonaktifkan shadow
                self._deactivate("absent", reason)
                return
        cached = None if self._local else self._latest_cached()
        if cached:
            try:
                self._from_dir(*cached)
                logger.warning("MLflow tidak terjangkau (%s); memakai model dari cache %s", reason, cached[1])
                return
            except Exception as exc:
                reason = f"{reason}; cache gagal: {type(exc).__name__}"
        self._deactivate("unavailable", reason)
        logger.warning("model %s tidak tersedia: %s", self.alias, reason)

    def _alias_changed(self) -> bool:
        """True bila alias di registry kini menunjuk versi lain (promote/rollback/retrain) atau dihapus."""
        if self._local:
            return False
        if self.version and "(cache)" in self.version:
            return True  # tadinya memakai cache: coba kembali ke MLflow
        try:
            version, _ = self._registry_version()
        except AliasMissing:
            return self.status == "ok"
        except Exception:
            return False  # MLflow sedang mati: tetap pakai model aktif
        return f"{REGISTERED_MODEL}/{version}" != self.version

    def start_background(self) -> None:
        def loop():
            while not self._stop.is_set():
                if self.status in ("loading", "unavailable") or self._alias_changed() or (
                        self.alias == "challenger" and self.status == "absent"):
                    self.load()
                self._stop.wait(self.retry_seconds)

        threading.Thread(target=loop, name=f"model-loader-{self.alias}", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------ inferensi
    def infer(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
        """(logits, embedding atau None bila model tidak punya keluaran embedding)."""
        with self._lock:
            session, outputs = self._session, list(self._outputs)
        if session is None:
            raise ModelUnavailable(self.error or "model belum dimuat")
        want = ["logits"] + (["embedding"] if "embedding" in outputs else [])
        res = session.run(want, {"image": x.astype(np.float32)})
        return res[0], (res[1] if len(res) > 1 else None)

    def logits(self, x: np.ndarray) -> np.ndarray:
        return self.infer(x)[0]

    def info(self) -> dict:
        with self._lock:
            meta = self.meta or {}
            return {"alias": self.alias, "status": self.status, "error": self.error, "version": self.version,
                    "name": meta.get("name"), "data_version": meta.get("data_version"), "smoke": meta.get("smoke", False)}
