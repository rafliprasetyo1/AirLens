"""Rekaman alat Beta (tools/recorder.html -> make import-beta-recordings): baca CSV, fitur dengan baseline clean_air
rekaman sendiri (sama dengan API), split waktu per label dengan purge, dan penolakan CSV yang tidak lengkap."""

import numpy as np
import pandas as pd
import pytest

from airlens.data import beta_gas
from airlens_trainer.import_beta_recordings import MV, read_recording, recording_features, recording_split

CFG = beta_gas.load_beta_config()


def _csv(tmp_path, per_label=60, clean_rows=60):
    rows, t = [], pd.Timestamp("2026-12-01T08:00:00Z")
    levels = {"clean_air": (900, 800, 1000, 850), "smoke": (1300, 1150, 1050, 1250), "none": (950, 820, 1010, 870)}
    for label, n in (("none", 5), ("clean_air", clean_rows), ("smoke", per_label)):
        for i in range(n):
            mv = levels[label]
            rows.append({"timestamp": (t + pd.Timedelta(seconds=2 * len(rows))).isoformat(), "uptime_s": len(rows) * 2,
                         "node_id": "lite-01", **dict(zip(MV.values(), mv)), "label": label})
    p = tmp_path / "rec.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    return p


def test_features_use_clean_air_baseline_of_the_recording(tmp_path):
    df = recording_features(read_recording(_csv(tmp_path)), CFG)
    assert set(df["label"]) == {"clean_air", "smoke"}                       # baris tanpa label dibuang
    clean = df[df["label"] == "clean_air"]
    assert np.allclose(clean[["r_mq2", "r_mq3", "r_mq7", "r_mq135"]], 1.0)
    smoke = df[df["label"] == "smoke"]
    assert (smoke["r_mq2"] < 0.8).all() and (smoke["r_mq135"] < 0.8).all()   # tegangan naik -> Rs/R0 turun
    assert list(df[beta_gas.feature_names(CFG)].columns) == beta_gas.feature_names(CFG)


def test_needs_enough_clean_air_rows(tmp_path):
    with pytest.raises(ValueError, match="Clean air"):
        recording_features(read_recording(_csv(tmp_path, clean_rows=3)), CFG)


def test_rejects_csv_without_required_columns(tmp_path):
    p = tmp_path / "bad.csv"
    pd.DataFrame({"timestamp": ["x"], "mq2_mv": [1]}).to_csv(p, index=False)
    with pytest.raises(ValueError, match="kolom tidak ada"):
        read_recording(p)


def test_time_split_per_label_with_purge(tmp_path):
    df = recording_features(read_recording(_csv(tmp_path, per_label=100, clean_rows=100)), CFG)
    split = recording_split(df, train_frac=0.7, purge=5)
    for label in ("clean_air", "smoke"):
        s = split[df["label"] == label].tolist()
        assert s[:65] == ["train"] * 65 and s[-25:] == ["test"] * 25 and set(s[65:75]) == {""}
