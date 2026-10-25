import numpy as np
import pytest

from airlens.models.metrics import (
    classification_metrics,
    expected_calibration_error,
    risk_coverage,
    selective_metrics,
)


def test_classification_metrics_simple():
    y = np.array([0, 0, 1, 1, 2, 2])
    p = np.array([0, 0, 1, 0, 2, 1])
    m = classification_metrics(y, p, 3)
    assert m["accuracy"] == pytest.approx(4 / 6)
    assert m["recall_per_class"] == pytest.approx([1.0, 0.5, 0.5])
    assert m["balanced_accuracy"] == pytest.approx(2 / 3)
    assert m["confusion_matrix"] == [[2, 0, 0], [1, 1, 0], [0, 1, 1]]


def test_ece_zero_when_confidence_equals_accuracy():
    # 10 prediksi dengan keyakinan 0,8 dan tepat 8 benar.
    probs = np.tile([0.8, 0.2], (10, 1))
    y = np.array([0] * 8 + [1] * 2)
    assert expected_calibration_error(probs, y) == pytest.approx(0.0, abs=1e-9)


def test_ece_overconfident():
    probs = np.tile([0.99, 0.01], (10, 1))
    y = np.array([0] * 5 + [1] * 5)
    assert expected_calibration_error(probs, y) == pytest.approx(0.49)


def test_selective_and_risk_coverage():
    probs = np.array([[0.9, 0.1], [0.8, 0.2], [0.55, 0.45], [0.6, 0.4]])
    y = np.array([0, 0, 1, 0])
    s = selective_metrics(probs, y, threshold=0.7, n_classes=2)
    assert s["rejected_fraction"] == 0.5 and s["accepted_accuracy"] == 1.0 and s["n_accepted"] == 2
    cov, acc, _ = risk_coverage(probs, y)
    assert cov[-1] == 1.0 and acc[0] == 1.0 and acc[-1] == pytest.approx(0.75)
