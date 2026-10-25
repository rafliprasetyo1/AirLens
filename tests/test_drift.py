import numpy as np
import pytest

from airlens.monitoring.drift import drift_table, ks, psi
from airlens.monitoring.signature import fit_pca, project

rng = np.random.default_rng(0)
REF = rng.normal(0.5, 0.1, 2000)


def test_psi_near_zero_for_same_distribution():
    assert psi(REF, rng.normal(0.5, 0.1, 2000)) < 0.05


def test_corrected_rule_keeps_false_alarms_low_on_small_samples():
    # 8 fitur tanpa drift, n=60: aturan (PSI terkoreksi >= 0,1 dan KS p < 0,01) jarang menyala.
    alarms = 0
    for _ in range(200):
        t = drift_table({f: REF.tolist() for f in "abcdefgh"}, {f: rng.normal(0.5, 0.1, 60).tolist() for f in "abcdefgh"})
        alarms += any(d["psi_adj"] >= 0.1 and d["ks_p"] < 0.01 for d in t.values())
    assert alarms / 200 < 0.10


def test_psi_large_for_shifted_distribution():
    assert psi(REF, rng.normal(0.3, 0.1, 60)) > 0.5


def test_ks_detects_shift_only_when_present():
    assert ks(REF, rng.normal(0.5, 0.1, 500))[1] > 0.01
    assert ks(REF, rng.normal(0.3, 0.1, 500))[1] < 1e-6


def test_drift_table_skips_missing_and_reports_medians():
    t = drift_table({"a": REF.tolist(), "b": REF.tolist()}, {"a": [0.3] * 50 + [None], "b": []})
    assert set(t) == {"a"} and t["a"]["n"] == 50 and t["a"]["cur_median"] == pytest.approx(0.3)


def test_pca_projection_shapes_and_centering():
    emb = rng.normal(size=(300, 40))
    pca = fit_pca(emb, k=8)
    proj = project(emb, pca)
    assert proj.shape == (300, 8) and np.abs(proj.mean(axis=0)).max() < 1e-6
    assert project(emb[0], pca).shape == (1, 8)
