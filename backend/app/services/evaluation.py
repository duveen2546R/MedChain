from __future__ import annotations

import json
import logging
import math
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

TWIN_SCHEMA_VERSION = "medchain-twin-v1"


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))


def evaluate_weights(
    features: np.ndarray,
    labels: np.ndarray,
    weights: list[float],
) -> tuple[float, float]:
    """Score a logistic-regression weight vector [coef..., intercept]."""
    vector = np.asarray(weights, dtype=np.float64)
    if vector.shape[0] != features.shape[1] + 1:
        raise ValueError(
            f"Expected {features.shape[1] + 1} weights, received {vector.shape[0]}"
        )
    probabilities = sigmoid(features @ vector[:-1] + vector[-1])
    predictions = (probabilities >= 0.5).astype(np.int64)
    accuracy = float((predictions == labels).mean())
    clipped = np.clip(probabilities, 1e-12, 1 - 1e-12)
    log_loss = float(-(labels * np.log(clipped) + (1 - labels) * np.log(1 - clipped)).mean())
    return accuracy, log_loss


class DigitalTwin:
    """Synthetic stress-test set used to sandbox model updates before merging."""

    def __init__(self, features: np.ndarray, labels: np.ndarray, mean: np.ndarray, scale: np.ndarray):
        self._features = features
        self._labels = labels
        self._mean = mean
        self._scale = scale

    @classmethod
    def load(cls, path: str | None) -> "DigitalTwin | None":
        if not path:
            return None
        file = Path(path)
        if not file.exists():
            logger.warning("Digital twin file %s is missing; validation gate is disabled", file)
            return None
        payload = json.loads(file.read_text())
        if payload.get("schema_version") != TWIN_SCHEMA_VERSION:
            raise RuntimeError(f"Unsupported digital twin schema in {file}")
        features = np.asarray(payload["X"], dtype=np.float64)
        labels = np.asarray(payload["y"], dtype=np.int64)
        mean = np.asarray(payload["scaler"]["mean"], dtype=np.float64)
        scale = np.asarray(payload["scaler"]["scale"], dtype=np.float64)
        if features.ndim != 2 or features.shape[0] != labels.shape[0]:
            raise RuntimeError(f"Digital twin data in {file} is malformed")
        if mean.shape[0] != features.shape[1] or scale.shape[0] != features.shape[1]:
            raise RuntimeError(f"Digital twin scaler in {file} does not match its features")
        return cls(features, labels, mean, scale)

    @property
    def n_features(self) -> int:
        return int(self._features.shape[1])

    @property
    def expected_dimension(self) -> int:
        return self.n_features + 1

    def evaluate(self, weights: list[float]) -> tuple[float, float]:
        return evaluate_weights(self._features, self._labels, weights)

    def standardize(self, raw_features: list[float]) -> np.ndarray:
        vector = np.asarray(raw_features, dtype=np.float64)
        if vector.shape[0] != self.n_features:
            raise ValueError(f"Expected {self.n_features} features, received {vector.shape[0]}")
        if not np.all(np.isfinite(vector)):
            raise ValueError("Features must be finite numbers")
        return (vector - self._mean) / self._scale

    def predict_proba(self, raw_features: list[float], weights: list[float]) -> float:
        vector = np.asarray(weights, dtype=np.float64)
        if vector.shape[0] != self.expected_dimension:
            raise ValueError(
                f"Expected {self.expected_dimension} weights, received {vector.shape[0]}"
            )
        standardized = self.standardize(raw_features)
        probability = sigmoid(np.asarray([standardized @ vector[:-1] + vector[-1]]))[0]
        if math.isnan(probability):
            raise ValueError("Prediction produced an invalid probability")
        return float(probability)
