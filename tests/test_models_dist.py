"""Distribusi model (models-publish / models-pull): manifest, verifikasi sha256 (berkas rusak ditolak), impor ke MLflow
kosong ("mesin baru"), impor berulang tidak menggandakan, alias terpasang, dan API bisa memuat model hasil impor."""

import json
import os
import shutil
from pathlib import Path

import numpy as np
import pytest

lgb = pytest.importorskip("lightgbm")
onnx = pytest.importorskip("onnx")

from airlens_trainer import models_dist  # noqa: E402


def _onnx(path: Path):
    from onnx import TensorProto, helper

    x = helper.make_tensor_value_info("image", TensorProto.FLOAT, [1, 3, 224, 224])
    y = helper.make_tensor_value_info("logits", TensorProto.FLOAT, [1, 3])
    w = helper.make_tensor("w", TensorProto.FLOAT, [3, 3 * 224 * 224], np.zeros(3 * 3 * 224 * 224, np.float32))
    nodes = [helper.make_node("Flatten", ["image"], ["f"]), helper.make_node("Gemm", ["f", "w"], ["logits"], transB=1)]
    onnx.save(helper.make_model(helper.make_graph(nodes, "g", [x], [y], [w]), opset_imports=[helper.make_opsetid("", 17)], ir_version=8),
              str(path))


def _package(root: Path) -> Path:
    from airlens.data import beta_gas

    cfg = beta_gas.load_beta_config()
    aqi = root / "models" / "airlens-aqi"
    aqi.mkdir(parents=True)
    _onnx(aqi / "model.onnx")
    (aqi / "metadata.json").write_text(json.dumps({"name": "efficientnet_b0", "classes": ["low", "elevated", "high"],
                                                   "temperature": 1.0, "threshold": {"threshold": 0.5},
                                                   "data_version": "d" * 64, "profile": "kaggle",
                                                   "test_metrics": {"macro_f1": 0.61}}))
    beta = root / "models" / "airlens-beta-gas"
    beta.mkdir(parents=True)
    feats = beta_gas.feature_names(cfg)
    rng = np.random.default_rng(0)
    X, y = rng.normal(1, 0.1, (200, len(feats))), rng.integers(0, 4, 200)
    booster = lgb.train({"objective": "multiclass", "num_class": 4, "verbose": -1, "num_leaves": 4},
                        lgb.Dataset(X, y), num_boost_round=5)
    booster.save_model(str(beta / "model.lgb"))
    (beta / "metadata.json").write_text(json.dumps({"classes": beta_gas.class_names(cfg), "features": feats,
                                                    "data_version": "b" * 64, "profile": "laptop",
                                                    "test_metrics": {"macro_f1": 0.86}}))
    entries = []
    for name, kind, src in (("airlens-aqi", "onnx", "kaggle"), ("airlens-beta-gas", "lightgbm", "laptop")):
        folder = root / "models" / name
        files = {str(p.relative_to(root)): {"sha256": models_dist.sha256(p), "bytes": p.stat().st_size}
                 for p in sorted(folder.rglob("*")) if p.is_file()}
        entries.append({"name": name, "source_version": "7", "alias": "production", "kind": kind, "source": src,
                        "data_version": None, "metrics": {"macro_f1": 0.6}, "files": files})
    (root / "manifest.json").write_text(json.dumps({"format": 1, "created": "2026-11-22T00:00:00+00:00",
                                                    "git_commit": "abc", "models": entries}))
    return root


@pytest.fixture
def fresh_mlflow(tmp_path, monkeypatch):
    """MLflow kosong (SQLite) + tanpa database aplikasi: simulasi mesin baru."""
    monkeypatch.setenv("AIRLENS_DB", "none")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path / 'mlflow.db'}")
    monkeypatch.chdir(tmp_path)
    import mlflow

    from airlens.db.session import get_engine

    mlflow.set_tracking_uri(f"sqlite:///{tmp_path / 'mlflow.db'}")
    get_engine.cache_clear()
    yield tmp_path
    get_engine.cache_clear()
    mlflow.set_tracking_uri(None)


def test_verify_rejects_corrupted_or_missing_file(tmp_path):
    root = _package(tmp_path / "pkg")
    assert len(models_dist.verify_package(root)["models"]) == 2
    with open(root / "models" / "airlens-aqi" / "model.onnx", "ab") as f:
        f.write(b"x")
    with pytest.raises(models_dist.PackageError, match="rusak"):
        models_dist.verify_package(root)
    (root / "manifest.json").unlink()
    with pytest.raises(models_dist.PackageError, match="manifest"):
        models_dist.verify_package(root)


def test_pull_into_empty_mlflow_is_idempotent_and_sets_aliases(tmp_path, fresh_mlflow):
    from mlflow import MlflowClient

    from airlens.models import registry

    root = _package(tmp_path / "pkg")
    manifest = models_dist.verify_package(root)
    client = MlflowClient()
    first = [models_dist.register(e, root, client, None) for e in manifest["models"]]
    assert [r["status"] for r in first] == ["didaftarkan", "didaftarkan"]
    assert registry.alias_version("production", model="airlens-aqi") == first[0]["version"]
    assert registry.alias_version("production", model="airlens-beta-gas") == first[1]["version"]
    again = [models_dist.register(e, root, client, None) for e in manifest["models"]]
    assert [r["status"] for r in again] == ["sudah ada", "sudah ada"]
    assert [r["version"] for r in again] == [r["version"] for r in first]
    assert len(client.search_model_versions("name='airlens-aqi'")) == 1   # tidak dobel

    # API memuat model hasil impor dari registry yang sama
    from airlens_api.beta_model import BetaModelStore
    from airlens_api.model_store import ModelStore

    aqi = ModelStore(tmp_path / "cache", alias="production")
    aqi.load()
    assert aqi.status == "ok" and aqi.version == f"airlens-aqi/{first[0]['version']}"
    assert aqi.logits(np.zeros((1, 3, 224, 224), np.float32)).shape == (1, 3)
    beta = BetaModelStore(tmp_path / "cache" / "beta")
    beta.load()
    assert beta.status == "ok"
    out = beta.predict({f: 1.0 for f in beta.meta["features"]})
    assert out["class"] in beta.meta["classes"] and abs(out["shap"]["base"] + sum(out["shap"]["values"].values()) - out["shap"]["score"]) < 1e-6


def test_key_metrics_and_source():
    assert models_dist.source_of({"profile": "kaggle"}) == "kaggle" and models_dist.source_of({}) == "laptop"
    assert models_dist.key_metrics("airlens-beta-gas", {"test_metrics": {"macro_f1": 0.86452, "recall_smoke": 0.99}}) == \
        {"macro_f1": 0.8645, "recall_smoke": 0.99}
    assert models_dist.MODELS == ("airlens-aqi", "airlens-beta-gas")
