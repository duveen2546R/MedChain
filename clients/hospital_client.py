"""One hospital's participation in a MedChain training round.

Trains a real logistic-regression model on this hospital's local data, warm-started
from the current global model, and submits only the weight vector plus measured
metrics — raw data never leaves the node. Two data sources are supported:

  * a local CSV (real mode): pass --csv and --objective-id; the node fetches the
    objective's schema + scaler from the server and trains on the local file.
  * the built-in breast-cancer shard (demo mode): the default when --csv is omitted.

Usable as a CLI or imported by run_demo.py.
"""

from __future__ import annotations

import argparse

import numpy as np
import requests

from common import (
    evaluate,
    hospital_partition,
    load_csv_dataset,
    standardize_with,
    train_logistic,
)


def login(api: str, email: str, password: str) -> str:
    response = requests.post(
        f"{api}/auth/login", json={"email": email, "password": password}, timeout=30
    )
    response.raise_for_status()
    return response.json()["access_token"]


def fetch_schema(api: str, token: str, objective_id: str) -> dict:
    response = requests.get(
        f"{api}/training-objectives/{objective_id}/schema",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_global_weights(api: str, token: str, objective_id: str | None = None) -> list[float] | None:
    params = {"objective_id": objective_id} if objective_id else None
    response = requests.get(
        f"{api}/model-versions/current",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=30,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json().get("weights") or None


def _local_split(features: np.ndarray, labels: np.ndarray, index: int) -> tuple:
    """Deterministic 80/20 train/holdout split of this node's own rows."""
    rng = np.random.default_rng(1000 + index)
    order = rng.permutation(len(labels))
    cut = max(1, int(len(order) * 0.8))
    train, holdout = order[:cut], order[cut:] if len(order) > 1 else order[:1]
    return features[train], labels[train], features[holdout], labels[holdout]


def _load_training_data(api, token, objective_id, csv_path, index, total):
    """Return (train_x, train_y, holdout_x, holdout_y) for CSV mode or demo mode."""
    if csv_path and objective_id:
        schema = fetch_schema(api, token, objective_id)
        raw_x, y = load_csv_dataset(
            csv_path, schema["feature_columns"], schema["target_column"], schema["positive_label"]
        )
        std_x = standardize_with(raw_x, schema["scaler"]["mean"], schema["scaler"]["scale"])
        return _local_split(std_x, y, index)
    # Demo mode: a shard of the built-in breast-cancer dataset.
    return hospital_partition(index, total)


def participate(
    api: str,
    token: str,
    hospital_id: str,
    round_id: str,
    index: int,
    total: int,
    poison: bool = False,
    objective_id: str | None = None,
    csv_path: str | None = None,
) -> dict:
    train_x, train_y, holdout_x, holdout_y = _load_training_data(
        api, token, objective_id, csv_path, index, total
    )
    global_weights = fetch_global_weights(api, token, objective_id)
    weights = train_logistic(train_x, train_y, global_weights)
    accuracy, loss = evaluate(holdout_x, holdout_y, weights)

    if poison:
        weights = [-value for value in weights]

    response = requests.post(
        f"{api}/rounds/{round_id}/submissions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "hospital_id": hospital_id,
            "update": {
                "weights": weights,
                "metrics": {
                    "local_accuracy": round(accuracy, 4),
                    "loss": round(loss, 4),
                    "samples": len(train_y),
                },
            },
        },
        timeout=60,
    )
    response.raise_for_status()
    submission = response.json()
    return {
        "hospital_id": hospital_id,
        "status": submission["status"],
        "local_accuracy": round(accuracy, 4),
        "evaluated_accuracy": submission.get("evaluated_accuracy"),
        "samples": len(train_y),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit one hospital's real model update")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--hospital-id", required=True)
    parser.add_argument("--round-id", required=True)
    parser.add_argument("--index", type=int, required=True, help="This hospital's shard index")
    parser.add_argument("--total", type=int, default=3, help="Total number of hospitals")
    parser.add_argument("--objective-id", help="Objective to train for (enables CSV mode)")
    parser.add_argument("--csv", dest="csv_path", help="Path to this hospital's local training CSV")
    parser.add_argument("--poison", action="store_true", help="Submit negated weights (gate demo)")
    args = parser.parse_args()

    token = login(args.api, args.email, args.password)
    result = participate(
        args.api,
        token,
        args.hospital_id,
        args.round_id,
        args.index,
        args.total,
        args.poison,
        objective_id=args.objective_id,
        csv_path=args.csv_path,
    )
    print(result)


if __name__ == "__main__":
    main()
