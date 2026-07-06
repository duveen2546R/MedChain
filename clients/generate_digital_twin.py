"""Generate the server-side digital-twin stress-test set.

Fits per-class diagonal Gaussians on a held-out slice of the breast-cancer
dataset and samples synthetic patients from them, so the backend can evaluate
submitted model updates without holding any real patient rows.

Run once (requires scikit-learn):

    python clients/generate_digital_twin.py
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sklearn.datasets import load_breast_cancer

SEED = 42
SYNTHETIC_ROWS = 200
HOLDOUT_FRACTION = 0.25
OUTPUT = Path(__file__).resolve().parents[1] / "backend" / "app" / "data" / "digital_twin.json"


def main() -> None:
    dataset = load_breast_cancer()
    features = np.asarray(dataset.data, dtype=np.float64)
    labels = np.asarray(dataset.target, dtype=np.int64)

    # Global scaler over the full dataset; clients recompute the identical one.
    mean = features.mean(axis=0)
    scale = features.std(axis=0)
    scale[scale == 0] = 1.0

    rng = np.random.default_rng(SEED)
    holdout_parts: list[np.ndarray] = []
    holdout_labels: list[np.ndarray] = []
    for label in (0, 1):
        rows = np.flatnonzero(labels == label)
        rng.shuffle(rows)
        take = rows[: max(2, int(len(rows) * HOLDOUT_FRACTION))]
        holdout_parts.append(features[take])
        holdout_labels.append(labels[take])

    synthetic_x: list[np.ndarray] = []
    synthetic_y: list[np.ndarray] = []
    for label, part in zip((0, 1), holdout_parts):
        class_share = len(holdout_labels[label]) / sum(len(item) for item in holdout_labels)
        count = max(10, int(round(SYNTHETIC_ROWS * class_share)))
        class_mean = part.mean(axis=0)
        class_std = part.std(axis=0)
        class_std[class_std == 0] = 1e-6
        samples = rng.normal(loc=class_mean, scale=class_std, size=(count, features.shape[1]))
        synthetic_x.append(samples)
        synthetic_y.append(np.full(count, label, dtype=np.int64))

    twin_x = (np.vstack(synthetic_x) - mean) / scale
    twin_y = np.concatenate(synthetic_y)
    order = rng.permutation(len(twin_y))
    twin_x, twin_y = twin_x[order], twin_y[order]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "schema_version": "medchain-twin-v1",
                "n_features": int(features.shape[1]),
                "scaler": {"mean": mean.tolist(), "scale": scale.tolist()},
                "X": np.round(twin_x, 6).tolist(),
                "y": twin_y.tolist(),
                "generated_at": datetime.now(UTC).isoformat(),
                "seed": SEED,
            }
        )
    )
    print(f"Wrote {len(twin_y)} synthetic rows to {OUTPUT}")


if __name__ == "__main__":
    main()
