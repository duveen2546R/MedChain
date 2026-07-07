"""Shared dataset handling and training code for MedChain hospital clients.

Each hospital trains a logistic-regression diagnostic model on its OWN local
data; only the resulting weight vector and measured metrics leave the client.
Real deployments load a local CSV (`load_csv_dataset`) and standardize with the
scaler the server publishes for the objective (`standardize_with`), so every
participant preprocesses identically and weights are directly comparable. The
breast-cancer helpers below remain only to produce the sample/demo dataset.
"""

from __future__ import annotations

import csv

import numpy as np


def load_csv_dataset(
    path: str,
    feature_columns: list[str],
    target_column: str,
    positive_label: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Load raw (unstandardized) features + binary labels from a local CSV.

    Columns are selected in the exact order the objective's schema specifies, so
    the weight vector lines up with the server's scaler and validation set.
    """
    with open(path, newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"{path} has no data rows")
    missing = [c for c in [*feature_columns, target_column] if c not in rows[0]]
    if missing:
        raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")
    features = np.asarray(
        [[float(row[column]) for column in feature_columns] for row in rows], dtype=np.float64
    )
    labels = np.asarray(
        [1.0 if row[target_column] == positive_label else 0.0 for row in rows], dtype=np.float64
    )
    return features, labels


def standardize_with(features: np.ndarray, mean: list[float], scale: list[float]) -> np.ndarray:
    """Standardize raw features with the server-published scaler (clients never recompute it)."""
    mean_arr = np.asarray(mean, dtype=np.float64)
    scale_arr = np.asarray(scale, dtype=np.float64)
    scale_arr[scale_arr == 0] = 1.0
    return (features - mean_arr) / scale_arr


def load_standardized_dataset() -> tuple[np.ndarray, np.ndarray]:
    from sklearn.datasets import load_breast_cancer

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
