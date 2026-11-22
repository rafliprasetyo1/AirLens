"""Sensor Beta: validasi, baseline, histeresis, offline, token, reset, dan simulator.

Alur waktu diuji lewat fungsi layanan dengan `now` yang disuntikkan (tanpa menunggu sungguhan); endpoint diuji lewat
TestClient terhadap database airlens_test.
"""

import importlib.util
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import delete

import airlens
from airlens.db.models import SensorNode, SensorReading
from airlens.db.session import get_engine
from airlens_api import sensor
from airlens_api.sensor import SensorConfig, baseline_from, next_state, rebooted

T0 = datetime(2026, 11, 21, 8, 0, tzinfo=timezone.utc)
CFG = SensorConfig(warmup_seconds=10, baseline_samples=3, alert_ratio=0.6, alert_consecutive=2, recover_ratio=0.8,
                   offline_seconds=20, history_max_minutes=120)


@pytest.fixture(scope="module", autouse=True)
def _schema():
    cfg = Config(str(Path(airlens.__file__).parent / "db" / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _clean():
    with get_engine().begin() as c:
        c.execute(delete(SensorReading))
        c.execute(delete(SensorNode))


def at(s: float) -> datetime:
    return T0 + timedelta(seconds=s)


def rec(node, rs, t, uptime=None, cfg=CFG):
    return sensor.record_reading(get_engine(), cfg, node, rs, uptime, False, now=at(t))


# ------------------------------------------------------------------ logika murni
def test_baseline_is_median_of_first_n():
    assert baseline_from([10.0, 30.0], 3) is None
    assert baseline_from([10.0, 30.0, 20.0, 99.0], 3) == 20.0


@pytest.mark.parametrize("state,streak,ratio,expected", [
    ("normal", 0, 0.5, ("normal", 1)),   # satu kali rendah belum cukup
    ("normal", 1, 0.5, ("alert", 0)),    # dua kali berturut-turut -> alert
    ("normal", 1, 0.7, ("normal", 0)),   # rentetan putus
    ("alert", 0, 0.7, ("alert", 0)),     # di antara ambang: tetap alert (histeresis)
    ("alert", 0, 0.85, ("normal", 0)),   # pulih di atas 0,8
])
def test_hysteresis(state, streak, ratio, expected):
    assert next_state(state, streak, ratio, CFG) == expected


def test_reboot_detection():
    assert rebooted(120, 5) and not rebooted(120, 125) and not rebooted(None, 5) and not rebooted(120, None)


# ------------------------------------------------------------------ alur di database
def test_warmup_then_baseline_ignores_invalid_readings():
    assert rec("n1", 20.0, 0)["state"] == "warming_up"
    assert rec("n1", 5.0, 5)["state"] == "warming_up"           # masih pemanasan: tidak dipakai baseline
    assert rec("n1", 18.0, 10)["state"] == "warming_up"         # sampel 1
    assert rec("n1", -1, 12)["valid"] is False                  # kabel lepas: disimpan, tidak dihitung
    assert rec("n1", 22.0, 15)["state"] == "warming_up"         # sampel 2
    r = rec("n1", 20.0, 20)                                     # sampel 3 -> baseline = median(18, 22, 20)
    assert r["state"] == "normal" and r["ratio"] == pytest.approx(1.0)
    assert sensor.latest(get_engine(), CFG, "n1", now=at(21))["baseline_kohm"] == pytest.approx(20.0)


def _baseline(node, start=0):
    for i, t in enumerate((start, start + 10, start + 15, start + 20)):
        rec(node, 20.0, t, uptime=t)


def test_alert_needs_two_low_readings_and_recovers_with_hysteresis():
    _baseline("n2")
    assert rec("n2", 10.0, 25, uptime=25)["state"] == "normal"   # rasio 0,5 sekali
    assert rec("n2", 10.0, 30, uptime=30)["state"] == "alert"    # dua kali -> alert
    assert rec("n2", 14.0, 35, uptime=35)["state"] == "alert"    # rasio 0,7: tetap alert
    assert rec("n2", 17.0, 40, uptime=40)["state"] == "normal"   # rasio 0,85: pulih


def test_offline_after_twenty_seconds():
    _baseline("n3")
    assert sensor.latest(get_engine(), CFG, "n3", now=at(25))["online"] is True
    body = sensor.latest(get_engine(), CFG, "n3", now=at(41))
    assert body["online"] is False and body["seconds_since"] == pytest.approx(21.0)


def test_device_reboot_restarts_warmup():
    _baseline("n4")
    r = rec("n4", 20.0, 60, uptime=3)   # uptime mundur: ESP32 menyala lagi, pemanas dingin
    assert r["state"] == "warming_up" and r["ratio"] is None
    assert sensor.latest(get_engine(), CFG, "n4", now=at(61))["baseline_kohm"] is None


def test_history_window():
    _baseline("n5")
    rows = sensor.history(get_engine(), CFG, "n5", minutes=30, now=at(30))
    assert [r["state"] for r in rows] == ["warming_up", "warming_up", "warming_up", "normal"]
    assert sensor.history(get_engine(), CFG, "n5", minutes=1, now=at(10 * 60)) == []


# ------------------------------------------------------------------ endpoint
@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:9")
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    monkeypatch.delenv("SENSOR_TOKEN", raising=False)
    from airlens_api.main import app

    with TestClient(app) as c:
        yield c


def test_post_reading_format_from_esp32(client):
    r = client.post("/sensor/readings", json={"node_id": "lite-01", "mq2_rs_kohm": 17.92, "uptime_s": 125})
    assert r.status_code == 200 and r.json()["state"] == "warming_up"
    body = client.get("/sensor/latest", params={"node_id": "lite-01"}).json()
    assert body["simulated"] is False and body["online"] is True and body["warmup"]["needed"] > 0


@pytest.mark.parametrize("payload", [
    {"node_id": "lite 01", "mq2_rs_kohm": 1.0},             # spasi tidak boleh
    {"node_id": "lite-01"},                                 # tanpa nilai sensor
    {"node_id": "lite-01", "mq2_rs_kohm": "abc"},
    {"node_id": "lite-01", "mq2_rs_kohm": 1.0, "uptime_s": -5},
])
def test_invalid_payload_rejected(client, payload):
    assert client.post("/sensor/readings", json=payload).status_code == 422


def test_nan_rejected(client):
    r = client.post("/sensor/readings", content=b'{"node_id": "lite-01", "mq2_rs_kohm": NaN}',
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_disconnected_sensor_is_stored_but_invalid(client):
    r = client.post("/sensor/readings", json={"node_id": "lite-01", "mq2_rs_kohm": -1, "uptime_s": 10})
    assert r.status_code == 200 and r.json()["valid"] is False


def test_token_required_when_configured(client, monkeypatch):
    monkeypatch.setenv("SENSOR_TOKEN", "rahasia-uji")
    body = {"node_id": "lite-01", "mq2_rs_kohm": 17.0}
    assert client.post("/sensor/readings", json=body).status_code == 401
    assert client.post("/sensor/readings", json=body, headers={"X-Node-Token": "salah"}).status_code == 401
    assert client.post("/sensor/readings", json=body, headers={"X-Node-Token": "rahasia-uji"}).status_code == 200
    assert client.post("/sensor/baseline/reset", json={"node_id": "lite-01"}).status_code == 401
    r = client.post("/sensor/baseline/reset", json={"node_id": "lite-01"}, headers={"X-Node-Token": "rahasia-uji"})
    assert r.status_code == 200


def test_unknown_node(client):
    assert client.get("/sensor/latest", params={"node_id": "tidak-ada"}).status_code == 404
    assert client.post("/sensor/baseline/reset", json={"node_id": "tidak-ada"}).status_code == 404


def test_simulated_flag_and_nodes_list(client):
    client.post("/sensor/readings", json={"node_id": "sim-01", "mq2_rs_kohm": 18.0, "simulated": True})
    nodes = client.get("/sensor/nodes").json()
    assert nodes[0]["node_id"] == "sim-01" and nodes[0]["simulated"] is True
    assert client.get("/sensor/history", params={"node_id": "sim-01"}).json()["readings"][0]["valid"] is True


# ------------------------------------------------------------------ simulator
def _sim():
    path = Path(__file__).resolve().parents[1] / "scripts" / "sensor_sim.py"
    spec = importlib.util.spec_from_file_location("sensor_sim", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_simulator_spike_crosses_both_thresholds():
    sim = _sim()
    assert sim.spike_factor(100, first=360, every=240, length=45) == 1.0                  # sebelum lonjakan
    assert sim.spike_factor(360 + 20, first=360, every=240, length=45) < CFG.alert_ratio  # di puncak: < 0,6
    assert sim.spike_factor(360 + 45 + 29, first=360, every=240, length=45) > CFG.recover_ratio  # pulih: > 0,8
    assert sim.spike_factor(360 + 240 + 20, first=360, every=240, length=45) < CFG.alert_ratio   # berulang


def test_simulator_is_deterministic_with_seed():
    sim = _sim()
    a = [sim.rs_at(t, random.Random(1)) for t in range(0, 600, 5)]
    b = [sim.rs_at(t, random.Random(1)) for t in range(0, 600, 5)]
    assert a == b and min(a) > 0


def test_simulator_drives_states_end_to_end():
    """Sinyal simulator lewat logika server (waktu disuntikkan): Warming up -> Normal -> Alert -> Normal."""
    sim, rng, seen = _sim(), random.Random(0), []
    cfg = SensorConfig(warmup_seconds=180, baseline_samples=24)
    for t in range(0, 720, 5):
        state = sensor.record_reading(get_engine(), cfg, "sim-e2e", sim.rs_at(t, rng), t, True, now=at(t))["state"]
        if not seen or seen[-1] != state:
            seen.append(state)
    assert seen[:4] == ["warming_up", "normal", "alert", "normal"]
