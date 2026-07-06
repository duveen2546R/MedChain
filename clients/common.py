"""Shared dataset handling and training code for MedChain hospital clients.

Each hospital trains a logistic-regression diagnostic model on its own shard of
the breast-cancer dataset; only the resulting weight vector and measured
metrics leave the client. The standardization scaler matches the one shipped
with the backend's digital twin, so weights are directly comparable.
"""

from __future__ import annotations

import numpy as np
from sklearn.datasets import load_breast_cancer

WEIGHT_DIMENSION = 31  # 30 coefficients + intercept


def load_standardized_dataset() -> tuple[np.ndarray, np.ndarray]:
    dataset = load_breast_cancer()
    features = np.asarray(dataset.data, dtype=np.float64)
    labels = np.asarray(dataset.target, dtype=np.float64)
    mean = features.mean(axis=0)
    scale = features.std(axis=0)
    scale[scale == 0] = 1.0
    return (features - mean) / scale, labels


def hospital_partition(
    index: int,
    total: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Deterministic per-hospital shard with an 80/20 local train/holdout split."""
    features, labels = load_standardized_dataset()
    order = np.argsort(features[:, 0], kind="stable")
    rows = order[index::total]

    rng = np.random.default_rng(1000 + index)
    shuffled = rng.permutation(rows)
    cut = max(1, int(len(shuffled) * 0.8))
    train, holdout = shuffled[:cut], shuffled[cut:]
    return features[train], labels[train], features[holdout], labels[holdout]


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))


def train_logistic(
    features: np.ndarray,
    labels: np.ndarray,
    initial_weights: list[float] | None,
    epochs: int = 200,
    learning_rate: float = 0.5,
    l2: float = 1e-4,
) -> list[float]:
    """Full-batch gradient descent, warm-started from the global weights."""
    if initial_weights:
        weights = np.asarray(initial_weights, dtype=np.float64).copy()
    else:
        weights = np.zeros(features.shape[1] + 1, dtype=np.float64)
    if weights.shape[0] != features.shape[1] + 1:
        raise ValueError(f"Expected {features.shape[1] + 1} weights, received {weights.shape[0]}")

    count = features.shape[0]
    for _ in range(epochs):
        probabilities = sigmoid(features @ weights[:-1] + weights[-1])
        error = probabilities - labels
        weights[:-1] -= learning_rate * (features.T @ error / count + l2 * weights[:-1])
        weights[-1] -= learning_rate * error.mean()
    return [round(float(value), 8) for value in weights]


def evaluate(features: np.ndarray, labels: np.ndarray, weights: list[float]) -> tuple[float, float]:
    vector = np.asarray(weights, dtype=np.float64)
    probabilities = sigmoid(features @ vector[:-1] + vector[-1])
    predictions = (probabilities >= 0.5).astype(np.float64)
    accuracy = float((predictions == labels).mean())
    clipped = np.clip(probabilities, 1e-12, 1 - 1e-12)
    log_loss = float(-(labels * np.log(clipped) + (1 - labels) * np.log(1 - clipped)).mean())
    return accuracy, log_loss
