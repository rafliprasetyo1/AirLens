import numpy as np
import pytest
from scipy.special import softmax

from airlens.models.calibration import calibrated_probs, choose_threshold, fit_temperature, nll


def test_temperature_recovers_overconfidence():
    rng = np.random.default_rng(0)
    true_logits = rng.normal(0, 1.5, size=(4000, 5))
    y = np.array([rng.choice(5, p=p) for p in softmax(true_logits, axis=1)])
    overconfident = true_logits * 3.0  # model terlalu yakin 3x
    t = fit_temperature(overconfident, y)
    assert t == pytest.approx(3.0, rel=0.15)
    assert nll(overconfident, y, t) < nll(overconfident, y, 1.0)


def test_calibrated_probs_sum_to_one():
    p = calibrated_probs(np.array([[1.0, 2.0, 3.0]]), 2.0)
    assert p.sum() == pytest.approx(1.0)


def test_threshold_reaches_target_with_max_coverage():
    # Keyakinan menurun; 6 teratas benar, sisanya salah semua.
    conf = np.linspace(0.95, 0.5, 10)
    probs = np.stack([conf, 1 - conf], axis=1)
    y = np.array([0] * 6 + [1] * 4)
    r = choose_threshold(probs, y, target_accuracy=0.85, min_accepted=3)
    assert r["target_tercapai"]
    assert r["val_accepted_accuracy"] >= 0.85
    assert r["val_coverage"] == pytest.approx(0.7)  # 6 benar + 1 salah = 6/7 = 0.857
    assert r["threshold"] == pytest.approx(conf[6])


def test_threshold_unreachable_is_reported():
    probs = np.tile([0.6, 0.4], (20, 1))
    y = np.array([0, 1] * 10)
    r = choose_threshold(probs, y, target_accuracy=0.9, min_accepted=5)
    assert r["target_tercapai"] is False
    assert r["val_coverage"] == 1.0  # semua seri: tidak bisa dipisah


def test_ties_are_not_split():
    probs = np.array([[0.9, 0.1], [0.7, 0.3], [0.7, 0.3], [0.6, 0.4]])
    y = np.array([0, 0, 1, 0])
    r = choose_threshold(probs, y, target_accuracy=0.6, min_accepted=1)
    assert r["val_coverage"] in (0.25, 0.75, 1.0)
