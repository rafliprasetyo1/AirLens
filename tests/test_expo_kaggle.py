"""Prompt 7: token wajib di mode expo, arsip tanpa Docker (format lab, manifest, rahasia tidak ikut), pesan galat Kaggle,
dan registry tanpa database (AIRLENS_DB=none, dipakai kernel Kaggle)."""

import tarfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

import airlens


@pytest.fixture(scope="module", autouse=True)
def _schema():
    cfg = Config(str(Path(airlens.__file__).parent / "db" / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:9")
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    from airlens_api.main import app

    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("path,body,var", [
    ("/sensor/readings", {"node_id": "x1", "mq2_rs_kohm": 18.0}, "SENSOR_TOKEN"),
    ("/node/readings", {"node_id": "x1", "smoke_prob": 0.1}, "NODE_TOKEN"),
])
def test_expo_mode_requires_tokens(client, monkeypatch, path, body, var):
    monkeypatch.setenv("EXPO_MODE", "1")
    monkeypatch.setenv(var, "")
    r = client.post(path, json=body)
    assert r.status_code == 503 and var in r.json()["detail"]
    monkeypatch.setenv(var, "rahasia-uji-123")
    assert client.post(path, json=body).status_code == 401                          # token salah/tidak ada
    assert client.post(path, json=body, headers={"X-Node-Token": "rahasia-uji-123"}).status_code == 200
    monkeypatch.setenv("EXPO_MODE", "0")
    monkeypatch.setenv(var, "")
    assert client.post(path, json=body).status_code == 200                          # pengembangan: tanpa token boleh


def test_export_archive_format_manifest_and_secret_guard(tmp_path, monkeypatch):
    from airlens_trainer import export_archive
    from airlens_trainer.import_results import verify_manifest

    results, arts, logs, ml = tmp_path / "results", tmp_path / "artifacts", tmp_path / "logs", tmp_path / "mlflow"
    (results).mkdir()
    (results / "smoke_eval.json").write_text('{"test": {}}')
    (arts / "models" / "abc123" / "efficientnet_b0").mkdir(parents=True)
    (arts / "models" / "abc123" / "efficientnet_b0" / "metadata.json").write_text("{}")
    (logs / "lab_x").mkdir(parents=True)
    (logs / "lab_x" / "RINGKASAN.txt").write_text("ok")
    ml.mkdir()
    (ml / "mlflow.db").write_bytes(b"sqlite")
    monkeypatch.setattr(export_archive, "RESULTS_DIR", results)
    monkeypatch.setattr(export_archive, "ARTIFACTS_DIR", arts)
    monkeypatch.setenv("KAGGLE_KEY", "KGAT_bukan_rahasia_asli_123")
    archive = export_archive.build("kaggle", logs, ml, tmp_path / "out")
    assert archive.name.startswith("airlens_results_kaggle_") and archive.name.endswith(".tar.gz")
    with tarfile.open(archive) as t:
        t.extractall(tmp_path / "x", filter="data")
    root = next((tmp_path / "x").iterdir())
    assert verify_manifest(root) >= 5
    assert {"results", "artifacts", "logs", "mlflow.tar.gz", "ENVIRONMENT.txt", "MANIFEST.sha256"} <= {p.name for p in root.iterdir()}
    # nilai rahasia di berkas hasil -> arsip dibatalkan
    (results / "bocor.txt").write_text("token KGAT_bukan_rahasia_asli_123")
    with pytest.raises(SystemExit, match="KAGGLE_KEY"):
        export_archive.build("kaggle", logs, ml, tmp_path / "out2")


@pytest.mark.parametrize("text,needle", [
    ("Phone verification is required", "nomor HP"),
    ("You have exceeded your GPU quota", "Kuota GPU"),
    ("401 Unauthorized", "Kredensial"),
    ("404 Not Found", "tidak ditemukan"),
])
def test_kaggle_error_hints(text, needle):
    from airlens_trainer.kaggle_ops import explain

    assert needle in explain(text)


def test_registry_without_database(monkeypatch, tmp_path):
    import mlflow
    from mlflow import MlflowClient

    from airlens.db.session import get_engine
    from airlens.models import registry

    monkeypatch.setenv("AIRLENS_DB", "none")
    get_engine.cache_clear()
    try:
        assert get_engine() is None
        mlflow.set_tracking_uri(f"sqlite:///{tmp_path / 'm.db'}")
        monkeypatch.chdir(tmp_path)
        mlflow.set_experiment("x")
        with mlflow.start_run() as r:
            mlflow.log_param("a", 1)
        c = MlflowClient()
        c.create_registered_model("m-test")
        mv = c.create_model_version("m-test", "file:///tmp/x", r.info.run_id)
        registry.record_registration(None, mv.version, "candidate", {"val_metrics": {}}, model="m-test")
        assert registry.set_production(None, mv.version, model="m-test") is None
        assert registry.alias_version("production", model="m-test") == str(mv.version)
        registry.set_challenger(None, mv.version, model="m-test")
        registry.mark_rolled_back(None, mv.version, model="m-test")
        assert registry.previous_production(None, mv.version, model="m-test") is None
    finally:
        mlflow.set_tracking_uri(None)
        get_engine.cache_clear()
