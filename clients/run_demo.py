"""End-to-end MedChain demo: real bring-your-own-CSV federated learning.

Generates per-hospital CSVs and a labeled validation CSV from the built-in
breast-cancer dataset (so it runs with no external data), then drives the REAL
pipeline: the coordinator uploads the validation CSV → the server derives the
feature schema + scaler → each hospital trains on its OWN CSV and submits only
weights → the backend gates, aggregates, and records contributions on-chain.

    python clients/run_demo.py --admin-email admin@... --admin-password ... --rounds 3
    python clients/run_demo.py ... --poison 2   # hospital 3 submits poisoned weights
"""

from __future__ import annotations

import argparse
import csv
import sys
import tempfile
from pathlib import Path

import numpy as np
import requests

from hospital_client import login, participate

SPECIALTY = "Oncology"


def api_call(method: str, api: str, path: str, token: str, expected: set[int], **kwargs) -> requests.Response:
    response = requests.request(
        method, f"{api}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=60, **kwargs
    )
    if response.status_code not in expected:
        sys.exit(f"{method} {path} failed ({response.status_code}): {response.text}")
    return response


def prepare_csv_datasets(total: int) -> tuple[str, list[str], list[int]]:
    """Write a validation CSV + one training CSV per hospital from the built-in dataset.
    Returns (validation_csv_text, per_hospital_csv_paths, per_hospital_row_counts)."""
    from sklearn.datasets import load_breast_cancer

    dataset = load_breast_cancer()
    columns = [name.replace(" ", "_") for name in dataset.feature_names]
    features = np.asarray(dataset.data, dtype=np.float64)
    labels = np.asarray(dataset.target, dtype=np.int64)  # 1 == benign, 0 == malignant

    rng = np.random.default_rng(7)
    order = rng.permutation(len(labels))
    val_cut = int(len(order) * 0.2)
    val_idx, train_idx = order[:val_cut], order[val_cut:]

    workdir = Path(tempfile.mkdtemp(prefix="medchain_demo_"))

    def write_csv(path: Path, indices: np.ndarray) -> None:
        with open(path, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([*columns, "diagnosis"])
            for i in indices:
                label = "benign" if labels[i] == 1 else "malignant"
                writer.writerow([*(f"{value:.6f}" for value in features[i]), label])

    validation_path = workdir / "validation.csv"
    write_csv(validation_path, val_idx)

    paths: list[str] = []
    counts: list[int] = []
    for index in range(total):
        shard = train_idx[index::total]
        path = workdir / f"hospital_{index + 1}.csv"
        write_csv(path, shard)
        paths.append(str(path))
        counts.append(len(shard))
    print(f"Prepared demo CSVs in {workdir} ({len(columns)} features)")
    return validation_path.read_text(), paths, counts


def seed_hospital(api: str, admin_token: str, index: int, samples: int, password: str) -> dict:
    email = f"hospital{index + 1}@demo.medchain"
    hospital_id = f"hsp_demo_{index + 1}"
    # Invite-only onboarding: the platform admin invites a hospital_admin (creating the org
    # inline), then we accept the invitation. Idempotent: on rerun login succeeds and we skip.
    try:
        token = login(api, email, password)
    except requests.HTTPError:
        invited = api_call(
            "POST", api, "/auth/invitations", admin_token, {201},
            json={
                "email": email,
                "role": "hospital_admin",
                "new_org": {"name": f"Demo Hospital {index + 1}", "type": "hospital"},
            },
        )
        invite_token = invited.json()["invitation"]["token"]
        registered = requests.post(
            f"{api}/auth/register",
            json={"token": invite_token, "name": f"Demo Hospital {index + 1}", "password": password},
            timeout=30,
        )
        if registered.status_code != 201:
            sys.exit(f"Hospital account registration failed: {registered.text}")
        token = login(api, email, password)
    org_id = api_call("GET", api, "/me", token, {200}).json()["org_id"]

    created = requests.post(
        f"{api}/hospitals",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "id": hospital_id,
            "name": f"Demo Hospital {index + 1}",
            "region": ["North", "South", "West"][index % 3],
            "samples": samples,
            "specialty": SPECIALTY,
            "org_id": org_id,
            "wallet_address": f"0x{index + 1:040x}",
        },
        timeout=30,
    )
    if created.status_code not in {200, 409}:
        sys.exit(f"Hospital creation failed: {created.text}")
    api_call("POST", api, f"/hospitals/{hospital_id}/blockchain/register", admin_token, {200})
    return {"hospital_id": hospital_id, "email": email, "index": index, "token": token}


def ensure_objective(api: str, admin_token: str, participants: int, validation_csv: str) -> str:
    """Create (or reuse) the demo objective, uploading the labeled validation CSV."""
    objectives = api_call("GET", api, "/training-objectives", admin_token, {200}).json()
    for item in objectives:
        if item["specialty"] == SPECIALTY and item.get("has_schema"):
            return item["id"]
    created = api_call(
        "POST", api, "/training-objectives", admin_token, {200},
        json={
            "name": "Breast Cancer Diagnosis (CSV)",
            "disease_category": "oncology",
            "specialty": SPECIALTY,
            "min_participants": participants,
            "validation_csv": validation_csv,
            "target_column": "diagnosis",
        },
    )
    return created.json()["id"]


def print_status(api: str, admin_token: str, hospitals: list[dict]) -> None:
    records = {
        item["id"]: item for item in api_call("GET", api, "/hospitals", admin_token, {200}).json()
    }
    for hospital in hospitals:
        record = records.get(hospital["hospital_id"], {})
        print(
            f"    {hospital['hospital_id']}: reputation {record.get('reputation')} "
            f"({record.get('status')})"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the MedChain federated demo")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", required=True)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--hospitals", type=int, default=3)
    parser.add_argument("--hospital-password", default="demo-hospital-pass-1")
    parser.add_argument("--poison", type=int, default=None, metavar="K",
                        help="1-based hospital number that submits poisoned weights")
    args = parser.parse_args()

    validation_csv, csv_paths, counts = prepare_csv_datasets(args.hospitals)

    admin_token = login(args.api, args.admin_email, args.admin_password)
    hospitals = [
        seed_hospital(args.api, admin_token, index, counts[index], args.hospital_password)
        for index in range(args.hospitals)
    ]
    for hospital in hospitals:
        hospital["csv"] = csv_paths[hospital["index"]]
    by_id = {hospital["hospital_id"]: hospital for hospital in hospitals}
    objective_id = ensure_objective(args.api, admin_token, args.hospitals, validation_csv)

    for round_number in range(1, args.rounds + 1):
        print(f"\n=== Round {round_number} ===")
        created = requests.post(
            f"{args.api}/rounds",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"objective_id": objective_id},
            timeout=30,
        )
        if created.status_code != 200:
            sys.exit(f"Round creation failed ({created.status_code}): {created.text}")
        training_round = created.json()
        selected = training_round["selected_hospital_ids"]
        unknown = [item for item in selected if item not in by_id]
        if unknown:
            sys.exit(f"Round selected non-demo hospitals {unknown}; deactivate them and retry")

        for hospital_id in selected:
            hospital = by_id[hospital_id]
            poison = args.poison is not None and hospital["index"] == args.poison - 1
            result = participate(
                args.api,
                hospital["token"],
                hospital_id,
                training_round["id"],
                hospital["index"],
                args.hospitals,
                poison=poison,
                objective_id=objective_id,
                csv_path=hospital["csv"],
            )
            marker = " (POISONED)" if poison else ""
            print(
                f"  {hospital_id}{marker}: {result['status']} - reported {result['local_accuracy']}, "
                f"twin-evaluated {result['evaluated_accuracy']}, samples {result['samples']}"
            )

        finished = api_call("GET", args.api, f"/rounds/{training_round['id']}", admin_token, {200}).json()
        print(f"  Round status: {finished['status']} - {finished['phase']}")
        model = requests.get(
            f"{args.api}/model-versions/current",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"objective_id": objective_id},
            timeout=30,
        )
        if model.status_code == 200:
            payload = model.json()
            print(
                f"  Global model {payload['version']}: reported {payload['accuracy']}%, "
                f"digital-twin evaluated {payload['evaluated_accuracy']}% "
                f"({payload['contributors']} contributors)"
            )
        print_status(args.api, admin_token, hospitals)

    verification = api_call("GET", args.api, "/blockchain/verify", admin_token, {200}).json()
    print(
        f"\nBlockchain: valid={verification['valid']} height={verification['height']} "
        f"transactions={verification['transactions']} authority={verification['authority']}"
    )


if __name__ == "__main__":
    main()
