"""Test alur /predict end-to-end di dalam proses (model ONNX mini, IQAir tiruan, database airlens_test)."""

import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import airlens
from airlens.db.models import IqairRequest, Prediction
from airlens.db.session import get_engine

onnx = pytest.importorskip("onnx")
from onnx import TensorProto, helper  # noqa: E402

CLASSES = ["good", "moderate", "usg", "unhealthy", "very_unhealthy"]


def _tiny_onnx(path: Path) -> None:
    """image (N,3,224,224) -> rata-rata kanal -> linear -> logits (N,5). Cukup untuk menguji alur, bukan akurasi."""
    w = np.array([[2.0, -1.0, 0.0, 0.5, -1.5], [0.5, 1.0, -0.5, 0.0, -1.0], [-1.0, 0.5, 1.0, -0.5, 0.0]], np.float32)
    graph = helper.make_graph(
        [helper.make_node("GlobalAveragePool", ["image"], ["gap"]),
         helper.make_node("Flatten", ["gap"], ["flat"]),
         helper.make_node("MatMul", ["flat", "w"], ["mm"]),
         helper.make_node("Add", ["mm", "b"], ["logits"])],
        "tiny",
        [helper.make_tensor_value_info("image", TensorProto.FLOAT, ["N", 3, 224, 224])],
        [helper.make_tensor_value_info("logits", TensorProto.FLOAT, ["N", 5])],
        [helper.make_tensor("w", TensorProto.FLOAT, w.shape, w.flatten()),
         helper.make_tensor("b", TensorProto.FLOAT, [5], np.zeros(5, np.float32))],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 10  # onnx 1.23 default IR 14; onnxruntime 1.31 menerima maksimal 13
    onnx.save(model, str(path))


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    d = tmp_path_factory.mktemp("bundle")
    _tiny_onnx(d / "model.onnx")
    q = list(np.linspace(0, 1, 21))
    (d / "metadata.json").write_text(json.dumps({
        "name": "tiny", "classes": CLASSES, "temperature": 1.0, "threshold": {"threshold": 0.0},
        "data_version": "test" * 16, "smoke": True,
        "hint_reference": {"contrast_rms": q, "dark_mean": q, "sky_lum": q},
    }))
    return d


@pytest.fixture(scope="module", autouse=True)
def _schema():
    cfg = Config(str(Path(airlens.__file__).parent / "db" / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


@pytest.fixture
def client(bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_BUNDLE_DIR", str(bundle))
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("MODEL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("IQAIR_API_KEY", "")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:9")  # MLflow tak terjangkau: challenger absent
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    from airlens_api.main import app

    with TestClient(app) as c:
        for _ in range(100):  # tunggu model termuat di thread latar
            if app.state.models.status == "ok":
                break
            time.sleep(0.05)
        yield c


def outdoor_jpeg(dark: float = 1.0, exif: bytes | None = None, size=(320, 240)) -> bytes:
    rng = np.random.default_rng(0)
    w, h = size
    arr = np.zeros((h, w, 3))
    arr[: h // 2] = [170, 190, 215]
    arr[h // 2 :] = rng.integers(40, 120, size=(h - h // 2, w, 3))
    buf = io.BytesIO()
    Image.fromarray((arr * dark).astype(np.uint8)).save(buf, format="JPEG", quality=90, **({"exif": exif} if exif else {}))
    return buf.getvalue()


def run(client, data: bytes, name="foto.jpg", mime="image/jpeg", **form):
    r = client.post("/predict", files={"file": (name, data, mime)}, data=form)
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    for _ in range(200):
        body = client.get(f"/jobs/{job_id}").json()
        if body["done"]:
            return job_id, body
        time.sleep(0.05)
    raise AssertionError("job tidak selesai")


def db_row(job_id: str) -> Prediction:
    with Session(get_engine()) as s:
        return s.scalars(select(Prediction).where(Prediction.job_id == job_id)).one()


# ---------------------------------------------------------------- alur normal
def test_valid_photo_full_flow(client):
    job_id, body = run(client, outdoor_jpeg())
    res = body["result"]
    assert res["status"] in ("ok", "uncertain")
    assert res["disclaimer"].startswith("Perkiraan")
    assert len(res["probabilities"]) == 5 and abs(sum(p["p"] for p in res["probabilities"]) - 1) < 1e-3
    assert {h["key"] for h in res["hints"]} == {"contrast_rms", "dark_mean", "sky_lum"}
    assert res["iqair"]["status"] == "tidak_tersedia" and res["iqair"]["code"] == "tanpa_lokasi"
    # Event tahap mengikuti urutan pipeline yang nyata.
    seq = [(e["stage"], e["status"]) for e in body["events"]]
    assert seq[:4] == [("periksa", "mulai"), ("periksa", "selesai"), ("analisis", "mulai"), ("analisis", "selesai")]
    assert seq[-1][0] == "selesai"
    row = db_row(job_id)
    assert row.status == res["status"] and row.model_version.startswith("lokal:") and row.data_version == "test" * 16
    assert row.photo_stored is False and row.image_sha256 and row.probabilities


def test_uncertain_when_below_threshold(client):
    from airlens_api.main import app

    app.state.models.meta["threshold"]["threshold"] = 0.99
    try:
        _, body = run(client, outdoor_jpeg())
    finally:
        app.state.models.meta["threshold"]["threshold"] = 0.0
    assert body["result"]["status"] == "uncertain" and body["result"]["category"] is None
    assert body["result"]["top_candidate"]["key"] in CLASSES


def test_sse_stream_contains_stages_and_result(client):
    job_id, _ = run(client, outdoor_jpeg())
    text = client.get(f"/jobs/{job_id}/events").text
    assert "event: tahap" in text and "event: hasil" in text
    assert text.index('"stage": "periksa"') < text.index("event: hasil")


# ---------------------------------------------------------------- penolakan unggahan
def test_fake_file_rejected(client):
    job_id, body = run(client, b"ini bukan gambar sama sekali" * 10, name="palsu.jpg")
    assert body["result"]["status"] == "rejected" and body["result"]["code"] == "bukan_gambar"
    assert db_row(job_id).reject_reason == "bukan_gambar"


def test_too_large_rejected(client):
    big = outdoor_jpeg() + b"\0" * (10 * 2**20 + 1)
    _, body = run(client, big)
    assert body["result"]["code"] == "terlalu_besar"


def test_gif_rejected(client):
    buf = io.BytesIO()
    Image.new("RGB", (200, 150), (120, 160, 220)).save(buf, format="GIF")
    _, body = run(client, buf.getvalue(), name="a.gif", mime="image/gif")
    assert body["result"]["code"] == "tipe_tidak_didukung"


def test_dark_photo_rejected(client):
    _, body = run(client, outdoor_jpeg(dark=0.12))
    assert body["result"]["code"] == "terlalu_gelap"


def test_unknown_city_422(client):
    r = client.post("/predict", files={"file": ("a.jpg", outdoor_jpeg(), "image/jpeg")}, data={"city_id": "atlantis"})
    assert r.status_code == 422


# ---------------------------------------------------------------- privasi
def _exif_with_gps() -> bytes:
    exif = Image.Exif()
    exif[0x010F] = "KameraUji"  # Make
    exif[0x8825] = {1: "S", 2: (6.0, 12.0, 0.0), 3: "E", 4: (106.0, 49.0, 0.0)}  # GPSInfo
    return exif.tobytes()


def test_exif_and_gps_removed_and_photo_only_stored_with_consent(client, tmp_path):
    data = outdoor_jpeg(exif=_exif_with_gps())
    assert Image.open(io.BytesIO(data)).getexif().get(0x8825)  # foto masukan memang punya GPS
    job_id, body = run(client, data, store_photo="true")
    assert body["result"]["photo_stored"] is True
    row = db_row(job_id)
    stored = tmp_path / "uploads" / f"{row.image_sha256}.jpg"
    assert stored.exists()
    out = Image.open(stored)
    assert len(out.getexif()) == 0 and "exif" not in out.info

    job2, body2 = run(client, data)  # tanpa persetujuan
    assert body2["result"]["photo_stored"] is False and db_row(job2).photo_stored is False
    assert len(list((tmp_path / "uploads").iterdir())) == 1


# ---------------------------------------------------------------- IQAir
def test_iqair_down_does_not_block_prediction(client, monkeypatch):
    from airlens_api.iqair import IQAirUnavailable
    from airlens_api.main import app

    def boom(*a, **k):
        raise IQAirUnavailable("jaringan", "IQAir tidak terjangkau (ConnectionError).")

    monkeypatch.setattr(app.state.iqair, "by_city", boom)
    _, body = run(client, outdoor_jpeg(), city_id="jakarta")
    res = body["result"]
    assert res["status"] in ("ok", "uncertain")
    assert res["iqair"] == {"status": "tidak_tersedia", "code": "jaringan", "message": "IQAir tidak terjangkau (ConnectionError)."}
    assert ("iqair", "gagal") in [(e["stage"], e["status"]) for e in body["events"]]


def test_iqair_ok_gives_comparison(client, monkeypatch):
    from airlens_api.iqair import Reading
    from airlens_api.main import app

    reading = Reading(id=1, city="Jakarta", state="Jakarta", country="Indonesia", aqi_us=99, main_pollutant="p2",
                      observed_at=datetime(2026, 10, 25, 4, tzinfo=timezone.utc), fetched_at=datetime.now(timezone.utc),
                      cached=False)
    monkeypatch.setattr(app.state.iqair, "by_city", lambda *a: reading)
    monkeypatch.setattr(app.state.pipeline, "_log", lambda *a, **k: None)  # id bacaan tiruan tidak ada di db
    _, body = run(client, outdoor_jpeg(), city_id="jakarta")
    iq = body["result"]["iqair"]
    assert iq["status"] == "ok" and iq["aqi_us"] == 99 and iq["category"]["key"] == "moderate"
    assert isinstance(iq["selisih_kategori"], int) and iq["jarak_ke_rentang"] >= 0


# ---------------------------------------------------------------- model tidak tersedia
def test_model_unavailable_is_reported(tmp_path, monkeypatch):
    empty = tmp_path / "kosong"
    empty.mkdir()
    monkeypatch.setenv("MODEL_BUNDLE_DIR", str(empty))
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("MODEL_CACHE_DIR", str(tmp_path / "cache"))
    from airlens_api.main import app

    with TestClient(app) as c:
        for _ in range(100):
            if app.state.models.status == "unavailable":
                break
            time.sleep(0.05)
        health = c.get("/health").json()
        assert health["status"] == "ok" and health["model"] == "unavailable"
        _, body = run(c, outdoor_jpeg())
    assert body["result"]["status"] == "error" and body["result"]["code"] == "model_tidak_tersedia"


# ---------------------------------------------------------------- klien IQAir: cache, kuota, galat
class FakeResp:
    def __init__(self, status, body):
        self.status_code, self._body, self.ok = status, body, 200 <= status < 300

    def json(self):
        return self._body


def _ok_body(aqi=80):
    return {"status": "success", "data": {"city": "Jakarta", "state": "Jakarta", "country": "Indonesia",
                                          "location": {"coordinates": [106.8, -6.2]},
                                          "current": {"pollution": {"ts": "2026-10-25T04:00:00.000Z", "aqius": aqi, "mainus": "p2"}}}}


@pytest.fixture
def iq(monkeypatch):
    from airlens_api import iqair

    eng = get_engine()
    with Session(eng) as s:
        s.execute(delete(IqairRequest))
        s.commit()
    calls = []

    def fake_get(url, params, timeout):
        calls.append(url)
        return fake_get.response

    fake_get.response = FakeResp(200, _ok_body())
    monkeypatch.setattr(iqair.requests, "get", fake_get)
    client = iqair.IQAirClient("kunci-uji", eng, ttl_seconds=900, per_minute=5, per_day=500)
    client.calls, client.fake = calls, fake_get
    return client


def test_iqair_cache_avoids_second_call(iq):
    a = iq.by_city("Jakarta", "Jakarta", "Indonesia")
    b = iq.by_city("Jakarta", "Jakarta", "Indonesia")
    assert len(iq.calls) == 1 and a.cached is False and b.cached is True and b.aqi_us == 80


def test_iqair_quota_per_minute(iq):
    from airlens_api.iqair import IQAirUnavailable

    with Session(iq.engine) as s:
        s.add_all([IqairRequest(endpoint="city", ok=True, status_code=200) for _ in range(5)])
        s.commit()
    with pytest.raises(IQAirUnavailable) as e:
        iq.by_city("Bandung", "West Java", "Indonesia")
    assert e.value.code == "kuota_menit" and iq.calls == []


def test_iqair_rate_limit_response(iq):
    from airlens_api.iqair import IQAirUnavailable

    iq.fake.response = FakeResp(429, {"status": "fail", "data": {"message": "call_limit_reached"}})
    with pytest.raises(IQAirUnavailable) as e:
        iq.by_city("Surabaya", "East Java", "Indonesia")
    assert e.value.code == "kuota"
    with Session(iq.engine) as s:  # panggilan gagal tetap dihitung ke kuota
        assert s.scalar(select(IqairRequest.ok).order_by(IqairRequest.id.desc()).limit(1)) is False


def test_iqair_without_key(iq):
    from airlens_api.iqair import IQAirClient, IQAirUnavailable

    with pytest.raises(IQAirUnavailable) as e:
        IQAirClient("", iq.engine).by_city("Medan", "North Sumatra", "Indonesia")
    assert e.value.code == "tanpa_kunci"


# ---------------------------------------------------------------- Fase 5: tanda tangan input & shadow mode
def test_input_signature_logged_for_drift(client):
    job_id, _ = run(client, outdoor_jpeg())
    stats = db_row(job_id).input_stats
    assert {"mean_lum", "std_lum", "mean_sat", "sky_frac", "contrast_rms", "dark_mean", "sky_lum"} <= set(stats)


def test_shadow_mode_logs_challenger_without_changing_response(bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_BUNDLE_DIR", str(bundle))
    monkeypatch.setenv("CHALLENGER_BUNDLE_DIR", str(bundle))
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("MODEL_CACHE_DIR", str(tmp_path / "cache"))
    from airlens_api.main import app

    with TestClient(app) as c:
        for _ in range(100):
            if app.state.models.status == "ok" and app.state.challenger.status == "ok":
                break
            time.sleep(0.05)
        assert c.get("/model").json()["challenger"]["status"] == "ok"
        job_id, body = run(c, outdoor_jpeg())
    assert "shadow" not in json.dumps(body["result"])  # hasil shadow tidak pernah dikirim ke pengguna
    with Session(get_engine()) as s:
        rows = s.scalars(select(Prediction).where(Prediction.job_id == job_id)).all()
    assert sorted(r.is_shadow for r in rows) == [False, True]


def test_broken_challenger_never_affects_user(client, monkeypatch):
    from airlens_api.main import app

    class Broken:
        status, version, meta = "ok", "airlens-aqi/99", {}

        def infer(self, x):
            raise RuntimeError("challenger rusak")

    monkeypatch.setattr(app.state.pipeline, "challenger", Broken())
    _, body = run(client, outdoor_jpeg())
    assert body["result"]["status"] in ("ok", "uncertain")
