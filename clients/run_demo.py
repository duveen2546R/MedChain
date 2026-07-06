"""End-to-end MedChain demo: 3 real federated hospitals across N rounds.

Seeds hospital accounts and on-chain registrations (idempotent), then drives
each round: every selected hospital trains locally and submits its real update,
the backend gates, aggregates, records contributions on-chain, and updates
reputations. Requires a platform administrator account.

    python clients/run_demo.py --admin-email admin@... --admin-password ... --rounds 3
    python clients/run_demo.py ... --poison 2   # hospital 3 submits poisoned weights
"""

from __future__ import annotations

import argparse
import sys

import requests

from common import hospital_partition
from hospital_client import login, participate

SPECIALTY = "Oncology"


def api_call(method: str, api: str, path: str, token: str, expected: set[int], **kwargs) -> requests.Response:
    response = requests.request(
        method, f"{api}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=60, **kwargs
    )
    if response.status_code not in expected:
        sys.exit(f"{method} {path} failed ({response.status_code}): {response.text}")
    return response


def seed_hospital(api: str, admin_token: str, index: int, total: int, password: str) -> dict:
    email = f"hospital{index + 1}@demo.medchain"
    hospital_id = f"hsp_demo_{index + 1}"
    registered = requests.post(
        f"{api}/auth/register",
        json={
            "name": f"Demo Hospital {index + 1}",
            "email": email,
            "password": password,
            "organization": f"Demo Hospital {index + 1}",
            "account_type": "hospital",
        },
        timeout=30,
    )
    if registered.status_code not in {201, 409}:
        sys.exit(f"Hospital account registration failed: {registered.text}")
    token = login(api, email, password)
    org_id = api_call("GET", api, "/me", token, {200}).json()["org_id"]

    train_x, _, _, _ = hospital_partition(index, total)
    created = requests.post(
        f"{api}/hospitals",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "id": hospital_id,
            "name": f"Demo Hospital {index + 1}",
            "region": ["North", "South", "West"][index % 3],
            "samples": len(train_x),
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


def ensure_objective(api: str, admin_token: str, participants: int) -> None:
    objectives = api_call("GET", api, "/training-objectives", admin_token, {200}).json()
    if any(item["specialty"] == SPECIALTY for item in objectives):
        return
    api_call(
        "POST",
        api,
        "/training-objectives",
        admin_token,
        {200},
        json={
            "name": "Breast Cancer Diagnosis",
            "disease_category": "oncology",
            "specialty": SPECIALTY,
            "min_participants": participants,
        },
    )


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

    admin_token = login(args.api, args.admin_email, args.admin_password)
    hospitals = [
        seed_hospital(args.api, admin_token, index, args.hospitals, args.hospital_password)
        for index in range(args.hospitals)
    ]
    by_id = {hospital["hospital_id"]: hospital for hospital in hospitals}
    ensure_objective(args.api, admin_token, args.hospitals)

    for round_number in range(1, args.rounds + 1):
        print(f"\n=== Round {round_number} ===")
        created = requests.post(
            f"{args.api}/rounds", headers={"Authorization": f"Bearer {admin_token}"}, json={}, timeout=30
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
