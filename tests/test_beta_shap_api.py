"""Revisi Beta SHAP, bagian B: skema lama dan baru, baseline per sensor, inferensi + SHAP per bacaan, endpoint explain,
pemicu berbasis model (dengan kalimat alasan), cadangan tanpa model, shadow challenger, dan replay simulator."""

import importlib.util
import json
import time
import uuid
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

import airlens
from airlens.data import beta_gas
from airlens_api import sensor
from airlens_api.beta_model import reason_sentence

lgb = pytest.importorskip("lightgbm")
CFG = beta_gas.load_beta_config()
LEVEL = {"NoGas": (750, 530, 610, 470), "Perfume": (745, 470, 640, 465),
         "Smoke": (600, 360, 575, 300), "Mixture": (585, 415, 450, 400)}


def _sim():
    path = Path(__file__).resolve().parents[1] / "scripts" / "sensor_sim.py"
    spec = importlib.util.spec_from_file_location("sensor_sim", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _synthetic(n=800, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for gas, (a, b, c, d) in LEVEL.items():
        for i in range(n):
            rows.append({"Serial Number": i, "MQ2": a + rng.normal(0, 5), "MQ3": b + rng.normal(0, 4), "MQ5": 1,
                         "MQ6": 1, "MQ7": c + rng.normal(0, 5), "MQ8": 1, "MQ135": d + rng.normal(0, 4), "Gas": gas})
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    from airlens_trainer.train_beta import train

    df = _synthetic()
    table, info = beta_gas.build(df, CFG)
    booster, *_ = train({**CFG, "model": {**CFG["model"], "n_estimators": 80}}, table)
    root = tmp_path_factory.mktemp("beta_bundle")
    booster.save_model(str(root / "model.txt"))
    (root / "metadata.json").write_text(json.dumps({
        "name": "lightgbm", "kind": "lightgbm", "classes": beta_gas.class_names(CFG),
        "features": beta_gas.feature_names(CFG), "data_version": "test" * 16,
        "test_metrics": {"macro_f1": 0.9, "f1": {}}, "dataset_citation": beta_gas.CITATION}))
    return root, info["clean_air_reference"]


@pytest.fixture(scope="module", autouse=True)
def _schema():
    cfg = Config(str(Path(airlens.__file__).parent / "db" / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


def _row_mv(gas: str, reference: dict) -> dict:
    a, b, c, d = LEVEL[gas]
    return _sim().dataset_mv({"MQ2": a, "MQ3": b, "MQ7": c, "MQ135": d}, reference)


@pytest.fixture
def api(bundle, tmp_path, monkeypatch):
    root, reference = bundle
    monkeypatch.setenv("BETA_BUNDLE_DIR", str(root))
    monkeypatch.delenv("BETA_CHALLENGER_BUNDLE_DIR", raising=False)
    monkeypatch.setenv("MODEL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:9")
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    monkeypatch.setenv("SENSOR_TOKEN", "")
    from airlens_api.main import TRIGGERS, app
    from airlens_api.triggers import TriggerEngine

    with TestClient(app) as client:
        for _ in range(300):
            if app.state.beta_model.status == "ok":
                break
            time.sleep(0.05)
        assert app.state.beta_model.status == "ok"
        monkeypatch.setattr(app.state, "sensor_cfg", sensor.SensorConfig(warmup_seconds=0, baseline_samples=3))
        monkeypatch.setattr(app.state, "triggers", TriggerEngine(TRIGGERS, sink=app.state.event_hub.sink))
        yield app, client, reference


def _post(client, node, mv, simulated=True):
    return client.post("/sensor/readings", json={"node_id": node, "uptime_s": 10, "simulated": simulated,
                                                 **{f"{k.lower()}_mv": v for k, v in mv.items()}})


# ------------------------------------------------------------------ skema
@pytest.mark.parametrize("payload", [
    {"node_id": "x1", "mq2_rs_kohm": 18.0, "mq2_mv": 900, "mq3_mv": 800, "mq7_mv": 1000, "mq135_mv": 850},  # dua format
    {"node_id": "x1", "mq2_mv": 900, "mq3_mv": 800},                                                    # tidak lengkap
    {"node_id": "x1", "mq2_mv": 9000, "mq3_mv": 800, "mq7_mv": 1000, "mq135_mv": 850},                  # di luar rentang
    {"node_id": "x1"},                                                                                  # kosong
])
def test_schema_rejects_bad_payloads(api, payload):
    _, client, _ = api
    assert client.post("/sensor/readings", json=payload).status_code == 422


def test_old_format_still_accepted(api):
    _, client, _ = api
    r = client.post("/sensor/readings", json={"node_id": f"old-{uuid.uuid4().hex[:6]}", "mq2_rs_kohm": 18.2})
    assert r.status_code == 200 and r.json()["state"] == "warming_up"


# ------------------------------------------------------------------ baseline, inferensi, SHAP, pemicu
def test_baseline_per_sensor_then_model_and_explain(api):
    app, client, ref = api
    node = f"b4-{uuid.uuid4().hex[:6]}"
    clean = _row_mv("NoGas", ref)
    states = [_post(client, node, clean).json() for _ in range(3)]
    assert states[-1]["state"] == "normal" and states[-1]["model_available"] is True
    latest = client.get(f"/sensor/latest?node_id={node}").json()
    assert latest["format"] == "mq4" and set(latest["sensors"]["baseline_rs_kohm"]) == {"MQ2", "MQ3", "MQ7", "MQ135"}
    assert all(abs(v - 1) < 0.01 for v in latest["sensors"]["ratios"].values())
    assert latest["model"]["class"] == "clean_air"

    smoky = _row_mv("Smoke", ref)
    r1, r2 = _post(client, node, smoky).json(), _post(client, node, smoky).json()
    assert r1["class"] == "smoke" and r1["state"] == "normal" and r2["state"] == "alert" and r2["label"] == "smoke"
    assert r2["reason"].startswith("Smoke likely: MQ-")

    for path in (f"/sensor/explain/latest?node_id={node}", f"/beta/explain/latest?node_id={node}"):
        ex = client.get(path).json()
        assert ex["model_available"] and ex["class"] == "smoke" and ex["simulated"] is True
        assert set(ex["shap"]) == set(beta_gas.feature_names(CFG))
        assert ex["expected_value"] + sum(ex["shap"].values()) == pytest.approx(ex["score"], abs=1e-6)   # additivity

    ev = client.get("/events/latest?room=booth").json()["event"]
    assert ev["kind"] == "invisible_gas" and ev["message"].startswith("Possible local smoke (Beta). Smoke likely:")
    assert ev["simulated"] is True and ev["trigger_values"][f"beta:{node}.beta_class"] == "smoke"

    # kembali bersih -> normal -> back_to_normal
    assert _post(client, node, clean).json()["state"] == "normal"
    hist = client.get(f"/sensor/history?node_id={node}&minutes=5").json()["readings"]
    assert [h["class"] for h in hist if h["class"]][-3:] == ["smoke", "smoke", "clean_air"] and hist[-1]["ratios"]


def test_alcohol_is_shown_but_does_not_alert(api):
    """Keputusan: kelas alkohol hanya ditampilkan (dataset latih lemah untuk alkohol -> peringatan palsu)."""
    _, client, ref = api
    node = f"b4-{uuid.uuid4().hex[:6]}"
    for _ in range(3):
        _post(client, node, _row_mv("NoGas", ref))
    res = [_post(client, node, _row_mv("Perfume", ref)).json() for _ in range(3)]
    assert all(r["class"] == "alcohol" for r in res)
    assert all(r["state"] == "normal" and r["label"] is None for r in res)


def test_fallback_rule_without_model(api, monkeypatch):
    app, client, ref = api
    monkeypatch.setattr(app.state.beta_model, "status", "unavailable")
    node = f"b4-{uuid.uuid4().hex[:6]}"
    for _ in range(3):
        _post(client, node, _row_mv("NoGas", ref))
    r = _post(client, node, _row_mv("Smoke", ref)).json()
    assert r["model_available"] is False and r["class"] is None and r["ratio"] < 1
    ex = client.get(f"/beta/explain/latest?node_id={node}").json()
    assert ex["model_available"] is False and ex["detail"] == "model not available"


def test_invalid_mv_is_stored_but_not_used(api):
    _, client, ref = api
    node = f"b4-{uuid.uuid4().hex[:6]}"
    bad = {**_row_mv("NoGas", ref), "MQ7": 0}
    r = _post(client, node, bad).json()
    assert r["valid"] is False and r["state"] == "warming_up"


def test_shadow_challenger_class_is_recorded(api, bundle, monkeypatch, tmp_path):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from airlens.db.models import SensorReading
    from airlens.db.session import get_engine
    from airlens_api.beta_model import BetaModelStore

    app, client, ref = api
    root, _ = bundle
    monkeypatch.setenv("BETA_CHALLENGER_BUNDLE_DIR", str(root))
    ch = BetaModelStore(tmp_path / "beta-ch", alias="challenger")
    ch.load()
    assert ch.status == "ok"
    monkeypatch.setattr(app.state, "beta_challenger", ch)
    node = f"b4-{uuid.uuid4().hex[:6]}"
    for _ in range(4):
        _post(client, node, _row_mv("NoGas", ref))
    with Session(get_engine()) as s:
        row = s.scalars(select(SensorReading).where(SensorReading.node_id == node)
                        .order_by(SensorReading.id.desc())).first()
    assert row.challenger_class == "clean_air" and row.predicted_class == "clean_air"


def test_model_summary_endpoint(api):
    _, client, _ = api
    body = client.get("/beta/model").json()
    assert body["available"] and body["model"] == "airlens-beta-gas" and "MultimodalGasData" in body["citation"]
    assert client.get("/beta/model/plots/tidak-ada.png").status_code == 404


# ------------------------------------------------------------------ fungsi murni
def test_next_state_model_hysteresis():
    cfg = sensor.SensorConfig()
    smoke = {"clean_air": .05, "alcohol": .05, "smoke": .6, "smoke_alcohol": .3}
    unsure = {"clean_air": .4, "alcohol": .1, "smoke": .3, "smoke_alcohol": .2}
    clean = {"clean_air": .9, "alcohol": .05, "smoke": .03, "smoke_alcohol": .02}
    assert sensor.next_state_model("normal", 0, smoke, None, cfg) == ("normal", 1, None)
    assert sensor.next_state_model("normal", 1, smoke, None, cfg) == ("alert", 0, "smoke")
    assert sensor.next_state_model("alert", 0, unsure, "smoke", cfg) == ("alert", 0, "smoke")    # di antara: tetap
    assert sensor.next_state_model("alert", 0, clean, "smoke", cfg) == ("normal", 0, None)
    assert sensor.next_state_model("normal", 1, unsure, None, cfg) == ("normal", 0, None)        # streak putus


def test_reason_sentence():
    text = reason_sentence("smoke", {"r_mq2": 0.81, "r_mq135": 0.64, "r_mq7": 0.94, "r_mq3": 0.7, "mq3_over_mq2": 0.86},
                           {"r_mq2": 0.1, "r_mq135": 1.92, "r_mq7": 0.41, "r_mq3": -0.3, "mq3_over_mq2": 0.05})
    assert text == "Smoke likely: MQ-135 at 0.64× clean air (+1.92), MQ-7 at 0.94× (+0.41), MQ-2 at 0.81× (+0.10)."
    assert reason_sentence("clean_air", {"r_mq2": 1}, {"r_mq2": -0.2}) == "Clean air."


def test_replay_mv_round_trips_to_dataset_ratios():
    sim = _sim()
    ref = {"MQ2": 758.0, "MQ3": 530.0, "MQ7": 610.0, "MQ135": 470.0}
    row = {"MQ2": 604, "MQ3": 361, "MQ7": 577, "MQ135": 300}
    mv = sim.dataset_mv(row, ref)
    clean_mv = sim.dataset_mv(ref, ref)
    base = {s: beta_gas.rs_from_mv(clean_mv[s]) for s in sim.SENSORS}
    feats = beta_gas.device_features(mv, base, CFG)
    for s in sim.SENSORS:
        assert feats[f"r_{s.lower()}"] == pytest.approx(row[s] / ref[s], rel=2e-3)
    assert [sim.replay_class(t, 240, 60) for t in (0, 239, 240, 300, 360, 420, 480, 540, 600)] == \
        ["NoGas", "NoGas", "NoGas", "Smoke", "NoGas", "Perfume", "NoGas", "Mixture", "NoGas"]
