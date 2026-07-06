"""One hospital's participation in a MedChain training round.

Trains a real logistic-regression model on this hospital's local data shard,
warm-started from the current global model, and submits only the weight vector
plus measured metrics. Usable as a CLI or imported by run_demo.py.
"""

from __future__ import annotations

import argparse

import requests

from common import evaluate, hospital_partition, train_logistic


def login(api: str, email: str, password: str) -> str:
    response = requests.post(
        f"{api}/auth/login", json={"email": email, "password": password}, timeout=30
    )
    response.raise_for_status()
    return response.json()["access_token"]


def fetch_global_weights(api: str, token: str) -> list[float] | None:
    response = requests.get(
        f"{api}/model-versions/current",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    weights = response.json().get("weights") or None
    return weights


def participate(
    api: str,
    token: str,
    hospital_id: str,
    round_id: str,
    index: int,
    total: int,
    poison: bool = False,
) -> dict:
    train_x, train_y, holdout_x, holdout_y = hospital_partition(index, total)
    global_weights = fetch_global_weights(api, token)
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
    parser.add_argument("--poison", action="store_true", help="Submit negated weights (gate demo)")
    args = parser.parse_args()

    token = login(args.api, args.email, args.password)
    result = participate(
        args.api, token, args.hospital_id, args.round_id, args.index, args.total, args.poison
    )
    print(result)


if __name__ == "__main__":
    main()
