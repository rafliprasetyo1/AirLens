from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import airlens
from airlens.config import load_profile
from airlens.db.models import MonitoringReport, Prediction
from airlens.db.session import get_engine
from airlens.monitoring import job

CLASSES = ["good", "moderate", "usg", "unhealthy", "very_unhealthy"]
rng = np.random.default_rng(1)
FEATS = ("mean_lum", "std_lum", "mean_sat", "sky_frac", "contrast_rms", "dark_mean", "sky_lum")
REFERENCE = {"classes": CLASSES, "monitoring_reference": {
    "features": {f: rng.normal(0.5, 0.1, 1000).round(4).tolist() for f in FEATS},
    "emb_proj": {"emb_pc1": rng.normal(0, 1, 1000).tolist()}}}


@pytest.fixture(scope="module", autouse=True)
def _schema():
    cfg = Config(str(Path(airlens.__file__).parent / "db" / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


@pytest.fixture
def window():
    eng = get_engine()
    with Session(eng) as s:
        s.execute(delete(Prediction))
        s.commit()
    return datetime.now(timezone.utc) - timedelta(seconds=1)


def add_rows(n, shift=0.0, status="ok", iqair=None, pred="moderate", shadow=None):
    eng = get_engine()
    with Session(eng) as s:
        for i in range(n):
            stats = {f: float(rng.normal(0.5 + shift, 0.1)) for f in FEATS} | {"emb_pca": [float(rng.normal(shift * 10, 1))]}
            s.add(Prediction(job_id=f"j{shift}{i}", model_version="airlens-aqi/9", data_version="x", status=status,
                             predicted_class=pred, confidence=0.8, input_stats=stats, iqair_aqi_us=iqair))
            if shadow:
                s.add(Prediction(job_id=f"j{shift}{i}", model_version="airlens-aqi/10", status="ok",
                                 predicted_class=shadow, confidence=0.7, is_shadow=True))
        s.commit()


def run_job(tmp_path, since):
    return job.run(get_engine(), load_profile("laptop"), tmp_path, tmp_path / "out", since=since,
                   until=datetime.now(timezone.utc) + timedelta(seconds=1), reference=REFERENCE, report_type="uji")


def test_no_drift_alert_on_normal_data(tmp_path, window):
    add_rows(150)  # n=150: alarm palsu aturan drift terukur ~0% (n=60: ~4%, bergantung seed)
    rep = run_job(tmp_path, window)
    assert [a for a in rep["alerts"] if a["type"] == "drift"] == []
    assert rep["retrain_recommended"] is False


def test_drift_alert_on_shifted_data_and_report_saved(tmp_path, window, monkeypatch):
    calls = []
    monkeypatch.setenv("MONITOR_WEBHOOK_URL", "http://webhook.uji/hook")
    monkeypatch.setattr(job.requests, "post", lambda url, json, timeout: calls.append((url, json)))
    add_rows(60, shift=0.3)
    rep = run_job(tmp_path, window)
    drifted = {a["feature"] for a in rep["alerts"] if a["type"] == "drift"}
    assert {"mean_lum", "embedding"} <= drifted and rep["retrain_recommended"] is True
    assert Path(rep["markdown"]).exists() and "Drift pada" in Path(rep["markdown"]).read_text()
    with Session(get_engine()) as s:
        row = s.get(MonitoringReport, rep["report_id"])
        assert row.retrain_triggered is True and row.alerts
    assert calls and calls[0][0] == "http://webhook.uji/hook"  # webhook dipanggil sekali dengan daftar peringatan


def test_insufficient_samples_do_not_alert(tmp_path, window):
    add_rows(5, shift=0.5)
    rep = run_job(tmp_path, window)
    assert not [a for a in rep["alerts"] if a["type"] == "drift"]
    assert any(a["type"] == "info" for a in rep["alerts"])


def test_rates_iqair_and_shadow(tmp_path, window):
    add_rows(50, iqair=180, pred="moderate", shadow="moderate")  # IQAir 180 = unhealthy; prediksi moderate (-2)
    add_rows(10, shift=0.0001, status="rejected")
    rep = run_job(tmp_path, window)
    assert rep["rejected_rate"] == pytest.approx(10 / 60, abs=1e-3)  # dibulatkan 4 desimal
    assert rep["iqair"]["n"] == 50 and rep["iqair"]["rata_selisih_absolut"] == 2.0
    assert any(a["type"] == "iqair" for a in rep["alerts"])
    assert rep["shadow"]["n"] == 50 and rep["shadow"]["sepakat_kelas"] == 1.0


def test_embedding_alert_needs_majority_of_components(tmp_path, window):
    ref = {"classes": CLASSES, "monitoring_reference": {"features": {},
           "emb_proj": {f"emb_pc{i}": rng.normal(0, 1, 1000).tolist() for i in range(1, 5)}}}
    eng = get_engine()
    with Session(eng) as s:  # hanya komponen 1 dari 4 yang bergeser (mis. pemandangan baru): tidak boleh menyala
        for i in range(150):
            s.add(Prediction(job_id=f"e{i}", model_version="airlens-aqi/9", status="ok", predicted_class="good",
                             confidence=0.9, input_stats={"emb_pca": [float(rng.normal(2, 1))] + rng.normal(0, 1, 3).tolist()}))
        s.commit()
    rep = job.run(eng, load_profile("laptop"), tmp_path, tmp_path / "out", since=window,
                  until=datetime.now(timezone.utc) + timedelta(seconds=1), reference=ref, report_type="uji")
    assert rep["embedding_drift_fraction"] == 0.25
    assert not [a for a in rep["alerts"] if a["type"] == "drift"]
