from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from backend.app.services.evaluation import DigitalTwin, evaluate_weights, sigmoid

FIXTURE = str(Path(__file__).parent / "data" / "twin_fixture.json")
GOOD_WEIGHTS = [4.0, 0.0, 0.0, 0.0]
POISONED_WEIGHTS = [-4.0, 0.0, 0.0, 0.0]


def test_sigmoid_bounds() -> None:
    values = sigmoid(np.asarray([-1000.0, 0.0, 1000.0]))
    assert values[0] == pytest.approx(0.0, abs=1e-9)
    assert values[1] == pytest.approx(0.5)
    assert values[2] == pytest.approx(1.0, abs=1e-9)


def test_evaluate_weights_on_fixture() -> None:
    twin = DigitalTwin.load(FIXTURE)
    assert twin is not None
    accuracy, loss = twin.evaluate(GOOD_WEIGHTS)
    assert accuracy == 1.0
    assert loss < 0.2
    poisoned_accuracy, _ = twin.evaluate(POISONED_WEIGHTS)
    assert poisoned_accuracy == 0.0


def test_twin_metadata_and_dimension() -> None:
    twin = DigitalTwin.load(FIXTURE)
    assert twin is not None
    assert twin.n_features == 3
    assert twin.expected_dimension == 4
    with pytest.raises(ValueError, match="Expected 4 weights"):
        twin.evaluate([0.1, 0.2])


def test_missing_twin_returns_none() -> None:
    assert DigitalTwin.load(None) is None
    assert DigitalTwin.load("/nonexistent/twin.json") is None


def test_predict_proba_standardizes_input() -> None:
    twin = DigitalTwin.load(FIXTURE)
    assert twin is not None
    confident = twin.predict_proba([3.0, 0.0, 0.0], GOOD_WEIGHTS)
    assert confident > 0.99
    uncertain = twin.predict_proba([0.0, 0.0, 0.0], GOOD_WEIGHTS)
    assert uncertain == pytest.approx(0.5)
    with pytest.raises(ValueError, match="Expected 3 features"):
        twin.predict_proba([1.0], GOOD_WEIGHTS)


def test_shipped_digital_twin_loads() -> None:
    shipped = Path(__file__).parents[1] / "app" / "data" / "digital_twin.json"
    twin = DigitalTwin.load(str(shipped))
    assert twin is not None
    assert twin.n_features == 30
    assert twin.expected_dimension == 31
    accuracy, _ = evaluate_weights(twin._features, twin._labels, [0.0] * 31)
    assert 0.0 <= accuracy <= 1.0
