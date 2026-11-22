"""Notifikasi kejadian: teks per jenis (termasuk Simulated dan Beta), tepat satu notifikasi per kejadian lewat
EventHub, jeda anti-spam, notifikasi pulih, Web Push (pywebpush di-mock), penghapusan subscription kedaluwarsa,
dan endpoint subscribe/unsubscribe/public-key."""

import json
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import airlens
from airlens.config import CONFIG_DIR
from airlens.db.models import PushSubscription
from airlens.db.session import get_engine
from airlens_api.events import EventHub
from airlens_api.push import PushSender, generate_keys, notification
from airlens_api.triggers import TriggerEngine, load_config


@pytest.fixture(scope="module", autouse=True)
def _schema():
    cfg = Config(str(Path(airlens.__file__).parent / "db" / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


@pytest.fixture
def clean_subs():
    with Session(get_engine()) as s:
        s.execute(delete(PushSubscription))
        s.commit()
    yield
    with Session(get_engine()) as s:
        s.execute(delete(PushSubscription))
        s.commit()


def _ev(kind, sources, simulated=False, message="m", values=None, eid=7, priority="high"):
    return {"id": eid, "kind": kind, "sources": sources, "simulated": simulated, "message": message,
            "trigger_values": values or {}, "priority": priority}


# ------------------------------------------------------------------ teks
@pytest.mark.parametrize("ev,title,url", [
    (_ev("smoke_confirmed", ["live:abc", "node:sim-full-01"]), "Smoke confirmed", "/beta.html"),
    (_ev("invisible_gas", ["node:sim-full-01"], message="Invisible gas detected, likely CO. Ventilate now"),
     "Invisible gas detected", "/beta.html"),
    (_ev("invisible_gas", ["beta:lite-01"], message="Possible local smoke (Beta). Smoke likely: MQ-135 at 0.72×"),
     "Possible local smoke or gas", "/beta.html"),
    (_ev("invisible_gas", ["beta:lite-01"], message="Alcohol/VOC detected (Beta). Alcohol/VOC likely: MQ-3"),
     "Alcohol or VOC detected", "/beta.html"),
    (_ev("visible_smoke", ["live:abc"], priority="medium"), "Visible smoke", "/beta.html"),
    (_ev("back_to_normal", [], priority="info"), "Back to normal", "/beta.html"),
])
def test_notification_text_per_kind(ev, title, url):
    n = notification(ev)
    assert n["title"] == title and n["url"] == url and n["tag"] == "airlens-event-7" and n["kind"] == ev["kind"]
    assert ev["message"] in n["body"]


def test_simulated_label_values_and_sources():
    n = notification(_ev("smoke_confirmed", ["live:x", "node:sim-full-01"], simulated=True,
                         values={"live:x.smoke_prob_median": 0.91, "node:sim-full-01.co": 48.2}))
    assert n["title"] == "[Simulated] Smoke confirmed" and n["simulated"] is True
    assert "Source: live:x, node:sim-full-01" in n["body"] and "smoke_prob_median 0.91" in n["body"]
    assert "Ventilate" in n["body"]


# ------------------------------------------------------------------ satu notifikasi per kejadian
class FakePush:
    def __init__(self):
        self.events = []

    def send_event(self, event, wait=False):
        self.events.append(event)


def test_each_event_triggers_exactly_one_push_with_cooldown_and_recovery():
    push = FakePush()
    hub = EventHub(push=push)
    t = [1000.0]
    engine = TriggerEngine(load_config(CONFIG_DIR / "triggers.yaml"), sink=hub.sink, clock=lambda: t[0])
    src = "node:push-test-01"
    for i in range(6):                       # kamera melihat asap terus: satu visible_smoke saja
        t[0] += 1
        engine.observe_camera(src, 0.95, True)
    assert [e["kind"] for e in push.events] == ["visible_smoke"]
    assert push.events[0]["notification"]["title"] == "[Simulated] Visible smoke"
    for i in range(40):                      # asap hilang > 30 s -> satu back_to_normal
        t[0] += 1
        engine.observe_camera(src, 0.05, True)
    engine.tick()
    assert [e["kind"] for e in push.events] == ["visible_smoke", "back_to_normal"]
    for i in range(6):                       # asap lagi dalam jeda anti-spam 60 s: tidak ada notifikasi baru
        t[0] += 1
        engine.observe_camera(src, 0.95, True)
    assert [e["kind"] for e in push.events] == ["visible_smoke", "back_to_normal"]


# ------------------------------------------------------------------ Web Push (mock pywebpush)
class Resp:
    def __init__(self, code):
        self.status_code = code


class GoneError(Exception):
    def __init__(self, code):
        super().__init__(f"push {code}")
        self.response = Resp(code)


def _add(endpoint):
    with Session(get_engine()) as s:
        s.add(PushSubscription(endpoint=endpoint, p256dh="B" * 87, auth="a" * 22))
        s.commit()


def test_push_sends_to_all_and_removes_expired(clean_subs):
    _add("https://push.example/ok-1")
    _add("https://push.example/gone-1")
    calls = []

    def fake_webpush(subscription_info, data, vapid_private_key, vapid_claims, ttl):
        calls.append((subscription_info["endpoint"], json.loads(data)))
        if "gone" in subscription_info["endpoint"]:
            raise GoneError(410)

    pub, priv = generate_keys()
    sender = PushSender(pub, priv, "mailto:test@example.com", webpush=fake_webpush)
    out = sender.send_event(_ev("smoke_confirmed", ["live:a", "beta:b"]), wait=True)
    assert out == {"sent": 1, "removed": 1, "errors": 0}
    assert {c[0] for c in calls} == {"https://push.example/ok-1", "https://push.example/gone-1"}
    assert calls[0][1]["title"] == "Smoke confirmed" and calls[0][1]["tag"] == "airlens-event-7"
    with Session(get_engine()) as s:
        left = [p.endpoint for p in s.scalars(select(PushSubscription))]
        ok = s.scalars(select(PushSubscription)).first()
    assert left == ["https://push.example/ok-1"] and ok.last_ok_at is not None


def test_push_disabled_without_vapid_keys():
    sender = PushSender("", "", webpush=lambda **k: pytest.fail("tidak boleh mengirim"))
    assert sender.enabled is False and sender.send_event(_ev("visible_smoke", []), wait=True)["sent"] == 0


def test_generated_keys_have_browser_format():
    import base64

    pub, priv = generate_keys()
    raw = base64.urlsafe_b64decode(pub + "=" * (-len(pub) % 4))
    assert len(raw) == 65 and raw[0] == 4          # titik P-256 tak terkompresi (applicationServerKey)
    assert len(base64.urlsafe_b64decode(priv + "=" * (-len(priv) % 4))) == 32


# ------------------------------------------------------------------ endpoint
@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:9")
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    from airlens_api.main import app

    with TestClient(app) as c:
        yield app, c


def test_subscribe_unsubscribe_and_public_key(client, clean_subs, monkeypatch):
    app, c = client
    monkeypatch.setattr(app.state, "push", PushSender("", ""))
    assert c.get("/push/public-key").status_code == 404
    pub, priv = generate_keys()
    monkeypatch.setattr(app.state, "push", PushSender(pub, priv))
    assert c.get("/push/public-key").json()["public_key"] == pub
    sub = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc123def456", "keys": {"p256dh": "B" * 87, "auth": "a" * 22}}
    assert c.post("/push/subscribe", json=sub).json() == {"subscribed": True}
    assert c.post("/push/subscribe", json=sub).status_code == 200            # ulang: tidak dobel
    with Session(get_engine()) as s:
        assert len(s.scalars(select(PushSubscription)).all()) == 1
    assert c.post("/push/subscribe", json={**sub, "endpoint": "http://insecure.example/x" * 2}).status_code == 422
    assert c.post("/push/unsubscribe", json={"endpoint": sub["endpoint"]}).json() == {"removed": 1}


def test_event_payload_carries_notification(client):
    app, c = client
    body = c.get("/events?minutes=600").json()["events"]
    if body:
        assert "notification" in body[0] and body[0]["notification"]["tag"].startswith("airlens-event-")
