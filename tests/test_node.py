"""Node lengkap: validasi, token, offline, dan simulator -> kejadian yang benar untuk tiap skenario."""

import importlib.util
import random
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import delete

import airlens
from airlens.config import CONFIG_DIR
from airlens.db.models import Event, NodeReading
from airlens.db.session import get_engine
from airlens_api.triggers import TriggerEngine, load_config

CFG = load_config(CONFIG_DIR / "triggers.yaml")
OK = {"node_id": "full-01", "uptime_s": 125, "smoke_prob": 0.912, "co_ppm": 3.1, "pm25": 6.2, "pm10": 8.0,
      "co2_ppm": 612, "voc_index": 104, "nox_index": 1, "temp_c": 27.9, "rh": 61.0}


def _sim():
    path = Path(__file__).resolve().parents[1] / "scripts" / "node_sim.py"
    spec = importlib.util.spec_from_file_location("node_sim", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_scenario(scenario: str, seconds: float, step: float = 2.0) -> list[dict]:
    sim, rng, events = _sim(), random.Random(0), []
    eng = TriggerEngine(CFG, sink=events.append)
    t = 0.0
    while t < seconds:
        r = sim.reading(scenario, t, rng)
        eng.observe_camera("node:sim-full-01", r["smoke_prob"], True, now=t)
        eng.observe_gas("node:sim-full-01", {"co": r["co_ppm"], "voc": r["voc_index"], "nox": r["nox_index"]}, True, now=t)
        eng.tick(now=t)
        t += step
    return events


# ------------------------------------------------------------------ simulator -> kejadian
@pytest.mark.parametrize("scenario,expected", [
    ("normal", []),
    ("invisible_gas", ["invisible_gas"]),
    ("visible_smoke", ["visible_smoke"]),
    ("smoke", ["visible_smoke", "smoke_confirmed"]),
])
def test_each_scenario_produces_its_event(scenario, expected):
    events = run_scenario(scenario, 50)
    assert [e["kind"] for e in events] == expected
    assert all(e["simulated"] for e in events)


def test_cycle_produces_all_three_kinds_and_back_to_normal():
    kinds = [e["kind"] for e in run_scenario("cycle", 450)]
    assert kinds == ["visible_smoke", "smoke_confirmed", "back_to_normal", "invisible_gas", "back_to_normal",
                     "visible_smoke", "back_to_normal"]


def test_invisible_gas_message_names_co():
    events = run_scenario("invisible_gas", 20)
    assert "likely CO" in events[0]["message"]


# ------------------------------------------------------------------ endpoint
@pytest.fixture(scope="module", autouse=True)
def _schema():
    cfg = Config(str(Path(airlens.__file__).parent / "db" / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:9")
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    monkeypatch.delenv("NODE_TOKEN", raising=False)
    with get_engine().begin() as c:
        c.execute(delete(NodeReading))
        c.execute(delete(Event))
    from airlens_api.main import app

    app.state.triggers.sources.clear()
    app.state.triggers.rooms.clear()
    with TestClient(app) as c:
        yield c


def test_reading_format_from_hardware_readme(client):
    assert client.post("/node/readings", json=OK).status_code == 200
    body = client.get("/node/latest", params={"node_id": "full-01"}).json()
    assert body["online"] is True and body["simulated"] is False and body["reading"]["voc_index"] == 104
    assert len(client.get("/node/history", params={"node_id": "full-01"}).json()["readings"]) == 1


def test_co_may_be_null(client):
    assert client.post("/node/readings", json={**OK, "co_ppm": None}).status_code == 200


@pytest.mark.parametrize("field,value", [("smoke_prob", 1.5), ("rh", 120), ("voc_index", 0), ("co_ppm", -1),
                                         ("temp_c", 200), ("node_id", "bad id")])
def test_out_of_range_rejected(client, field, value):
    assert client.post("/node/readings", json={**OK, field: value}).status_code == 422


def test_token_required_when_configured(client, monkeypatch):
    monkeypatch.setenv("NODE_TOKEN", "rahasia-node")
    assert client.post("/node/readings", json=OK).status_code == 401
    assert client.post("/node/readings", json=OK, headers={"X-Node-Token": "rahasia-node"}).status_code == 200


def test_offline_after_20_seconds(client):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy.orm import Session

    with Session(get_engine()) as s:
        s.add(NodeReading(node_id="old-01", received_at=datetime.now(timezone.utc) - timedelta(seconds=25), smoke_prob=0.1))
        s.commit()
    assert client.get("/node/latest", params={"node_id": "old-01"}).json()["online"] is False
    assert client.get("/node/latest", params={"node_id": "none"}).status_code == 404


def test_posting_readings_creates_events(client):
    for i in range(2):
        r = client.post("/node/readings", json={**OK, "node_id": "sim-full-01", "smoke_prob": 0.05, "co_ppm": 48,
                                                 "simulated": True})
    assert r.json()["events"] == ["invisible_gas"]
    ev = client.get("/events/latest").json()["event"]
    assert ev["kind"] == "invisible_gas" and ev["simulated"] is True and ev["sources"] == ["node:sim-full-01"]
