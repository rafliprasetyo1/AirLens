"""Trigger engine dua pemicu: tabel kejadian, histeresis, anti-spam, back_to_normal, ruangan, label simulasi, endpoint."""

import time
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import delete

import airlens
from airlens.config import CONFIG_DIR
from airlens.db.models import Event, SensorNode, SensorReading
from airlens.db.session import get_engine
from airlens_api.triggers import TriggerEngine, load_config

CFG = load_config(CONFIG_DIR / "triggers.yaml")


def engine(cfg=CFG):
    events = []
    return TriggerEngine(cfg, sink=events.append), events


def kinds(events):
    return [e["kind"] for e in events]


def cam(eng, src, prob, t, n=1, step=1.0, sim=False):
    out = []
    for i in range(n):
        out += eng.observe_camera(src, prob, sim, now=t + i * step)
    return out


def gas(eng, src, t, n=1, step=2.0, sim=False, **values):
    out = []
    for i in range(n):
        out += eng.observe_gas(src, values, sim, now=t + i * step)
    return out


# ------------------------------------------------------------------ tabel kejadian
def test_camera_and_gas_gives_smoke_confirmed():
    eng, ev = engine()
    gas(eng, "node:a", 0, n=2, voc=300)                 # gas naik dulu -> invisible_gas
    cam(eng, "node:a", 0.9, 4, n=3)                     # lalu kamera -> naik ke smoke_confirmed
    assert kinds(ev) == ["invisible_gas", "smoke_confirmed"]
    assert ev[-1]["priority"] == "high" and ev[-1]["message"] == "Smoke confirmed: camera and gas sensor agree"


def test_gas_only_co_is_invisible_gas_likely_co():
    eng, ev = engine()
    gas(eng, "node:a", 0, n=2, co=48)
    assert kinds(ev) == ["invisible_gas"] and "likely CO" in ev[0]["message"] and ev[0]["priority"] == "high"
    assert ev[0]["trigger_values"]["node:a.co"] == 48


def test_gas_only_voc_says_gas_detected():
    eng, ev = engine()
    gas(eng, "node:a", 0, n=2, voc=260, co=None)
    assert ev[0]["message"] == "Gas detected (VOC index)"


def test_camera_only_is_visible_smoke_medium():
    eng, ev = engine()
    cam(eng, "live:s1", 0.95, 0, n=3)
    assert kinds(ev) == ["visible_smoke"] and ev[0]["priority"] == "medium"


def test_beta_alert_counts_as_gas():
    eng, ev = engine()
    eng.observe_beta("beta:lite-01", True, 0.45, now=0)
    assert kinds(ev) == ["invisible_gas"] and "MQ-2" in ev[0]["message"]


# ------------------------------------------------------------------ histeresis
def test_camera_needs_three_of_five_and_ignores_single_frame():
    eng, ev = engine()
    cam(eng, "live:s1", 0.95, 0)                        # satu frame tinggi: tidak memicu
    cam(eng, "live:s1", 0.1, 1, n=2)
    assert ev == []
    cam(eng, "live:s1", 0.9, 3, n=2)                    # kini 3 dari 5 terakhir >= 0,70
    assert kinds(ev) == ["visible_smoke"]


def test_camera_exit_needs_30_seconds_below_040():
    eng, ev = engine()
    cam(eng, "live:s1", 0.9, 0, n=3)
    cam(eng, "live:s1", 0.1, 3, n=5)                    # median turun < 0,40 sejak t=5
    eng.tick(now=20)
    assert kinds(ev) == ["visible_smoke"]               # baru ±15 s: masih aktif
    cam(eng, "live:s1", 0.1, 36)
    assert kinds(ev) == ["visible_smoke", "back_to_normal"]


def test_gas_needs_two_in_a_row_and_60_seconds_to_exit():
    eng, ev = engine()
    gas(eng, "node:a", 0, co=35)
    gas(eng, "node:a", 2, co=10)                        # rentetan putus
    gas(eng, "node:a", 4, co=35)
    assert ev == []
    gas(eng, "node:a", 6, co=35)
    assert kinds(ev) == ["invisible_gas"]
    gas(eng, "node:a", 8, co=25)                        # di antara 20 dan 30: tetap aktif
    gas(eng, "node:a", 10, n=20, step=3, co=5)          # < 20 sejak t=10
    assert kinds(ev) == ["invisible_gas"]
    gas(eng, "node:a", 71, co=5)
    assert kinds(ev) == ["invisible_gas", "back_to_normal"]


def test_smoke_confirmed_does_not_step_down_while_clearing():
    eng, ev = engine()
    gas(eng, "node:a", 0, n=2, voc=300)
    cam(eng, "node:a", 0.9, 4, n=3)                     # smoke_confirmed
    cam(eng, "node:a", 0.1, 10, n=40)                   # kamera bersih (keluar setelah 30 s), VOC masih tinggi
    assert kinds(ev) == ["invisible_gas", "smoke_confirmed"]   # tidak ada "Gas detected" tambahan saat mereda
    gas(eng, "node:a", 60, n=40, step=2, voc=100)       # VOC turun < 180 selama 60 s
    assert kinds(ev) == ["invisible_gas", "smoke_confirmed", "back_to_normal"]


def test_switch_between_partial_kinds_is_reported():
    eng, ev = engine()
    cam(eng, "live:s1", 0.9, 0, n=3)                    # visible_smoke
    cam(eng, "live:s1", 0.1, 3, n=35)                   # kamera keluar -> back_to_normal
    eng.observe_beta("beta:x", True, 0.5, now=40)       # lalu gas saja
    assert kinds(ev) == ["visible_smoke", "back_to_normal", "invisible_gas"]


# ------------------------------------------------------------------ anti-spam dan pulih
def test_back_to_normal_sent_once():
    eng, ev = engine()
    eng.observe_beta("beta:x", True, 0.5, now=0)
    eng.observe_beta("beta:x", False, 0.9, now=5)
    eng.observe_beta("beta:x", False, 0.9, now=10)
    eng.tick(now=15)
    assert kinds(ev) == ["invisible_gas", "back_to_normal"]


def test_cooldown_suppresses_repeat_within_60_seconds():
    eng, ev = engine()
    eng.observe_beta("beta:x", True, 0.5, now=0)
    eng.observe_beta("beta:x", False, 0.9, now=10)      # back_to_normal
    eng.observe_beta("beta:x", True, 0.5, now=20)       # < 60 s sejak invisible_gas terakhir: ditahan
    assert kinds(ev) == ["invisible_gas", "back_to_normal"]
    eng.observe_beta("beta:x", True, 0.5, now=61)       # jeda lewat: dikirim
    assert kinds(ev) == ["invisible_gas", "back_to_normal", "invisible_gas"]


def test_source_timeout_ends_event():
    eng, ev = engine()
    cam(eng, "live:s1", 0.9, 0, n=3)
    eng.tick(now=70)                                    # sesi kamera hilang > 60 s
    assert kinds(ev) == ["visible_smoke", "back_to_normal"]


# ------------------------------------------------------------------ ruangan dan simulasi
def test_live_camera_and_beta_in_booth_combine():
    eng, ev = engine()
    eng.observe_beta("beta:lite-01", True, 0.4, now=0)
    cam(eng, "live:phone", 0.9, 1, n=3)
    assert kinds(ev) == ["invisible_gas", "smoke_confirmed"]
    assert ev[-1]["sources"] == ["beta:lite-01", "live:phone"] and ev[-1]["room"] == "booth"


def test_separate_rooms_do_not_combine():
    cfg = {**CFG, "rooms": {"default": "booth", "booth": {"sources": ["beta:*", "live:*"]},
                            "lab": {"sources": ["node:*"]}}}
    eng, ev = engine(cfg)
    gas(eng, "node:a", 0, n=2, co=40)                   # ruangan lab
    cam(eng, "live:phone", 0.9, 4, n=3)                 # ruangan booth
    assert sorted((e["room"], e["kind"]) for e in ev) == [("booth", "visible_smoke"), ("lab", "invisible_gas")]


def test_simulated_source_labels_event():
    eng, ev = engine()
    gas(eng, "node:sim-full-01", 0, n=2, sim=True, co=40)
    assert ev[0]["simulated"] is True
    eng2, ev2 = engine()
    gas(eng2, "node:full-01", 0, n=2, co=40)
    assert ev2[0]["simulated"] is False


# ------------------------------------------------------------------ endpoint + Beta lewat API
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
    monkeypatch.delenv("SENSOR_TOKEN", raising=False)
    with get_engine().begin() as c:
        c.execute(delete(Event))
        c.execute(delete(SensorReading))
        c.execute(delete(SensorNode))
    from airlens_api.main import app

    app.state.triggers.sources.clear()
    app.state.triggers.rooms.clear()
    with TestClient(app) as c:
        yield app, c


def test_events_endpoints_store_and_list(client):
    app, c = client
    app.state.triggers.observe_beta("beta:lite-01", True, 0.4, simulated=True)
    body = c.get("/events/latest", params={"room": "booth"}).json()
    assert body["event"]["kind"] == "invisible_gas" and body["event"]["simulated"] is True
    assert body["state"]["gas"] is True and body["state"]["current"] == "invisible_gas"
    assert [e["kind"] for e in c.get("/events", params={"minutes": 5}).json()["events"]] == ["invisible_gas"]


def test_event_hub_delivers_from_worker_thread_to_listener(client):
    """Kejadian dari thread pool (endpoint sinkron) sampai ke antrean pendengar SSE di event loop."""
    import asyncio
    import threading

    from airlens_api.events import EventHub

    async def scenario():
        hub = EventHub()
        hub.attach_loop(asyncio.get_running_loop())
        q = hub.subscribe()
        ev = {"room": "booth", "kind": "visible_smoke", "priority": "medium", "message": "Visible smoke, check the room",
              "sources": ["live:s9"], "trigger_values": {}, "simulated": False, "at": time.time()}
        threading.Thread(target=hub.sink, args=(ev,)).start()
        got = await asyncio.wait_for(q.get(), timeout=5)
        hub.unsubscribe(q)
        return got

    got = asyncio.run(scenario())
    assert got["kind"] == "visible_smoke" and got["id"] > 0   # tersimpan di tabel events, lalu disiarkan


def test_events_stream_route_is_sse(client):
    app, c = client
    assert app.url_path_for("stream") == "/events/stream"
