from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Hospital, Organization, TrainingObjective, User
from backend.app.security import hash_password
from backend.app.services.blockchain import BlockchainService
from backend.tests.fakes import CapturingNotificationService, MemoryArtifactStore, MemoryRepository

TEST_SECRET = "test-secret-key-that-is-longer-than-thirty-two-characters"
TEST_PASSWORD = "test-password-123"
TWIN_FIXTURE = str(Path(__file__).parent / "data" / "twin_fixture.json")


async def seed_test_records(
    repo: MemoryRepository,
    settings: Settings,
    blockchain: BlockchainService,
) -> None:
    platform = await repo.put(
        "organizations",
        Organization(id="org_platform", name="Platform", type="platform", tier="internal"),
    )
    await repo.put(
        "users",
        User(
            id="usr_admin",
            email="admin@example.com",
            name="Admin",
            role="platform_admin",
            org_id=platform.id,
            password_hash=hash_password(TEST_PASSWORD, settings),
        ),
    )
    await repo.put(
        "users",
        User(
            id="usr_auditor",
            email="auditor@example.com",
            name="Auditor",
            role="auditor",
            org_id=platform.id,
            password_hash=hash_password(TEST_PASSWORD, settings),
        ),
    )

    hospitals = [
        Hospital(id="h1", org_id="org_h1", name="Hospital One", region="North", samples=1000, specialty="Radiology", wallet_address="0x0000000000000000000000000000000000000001"),
        Hospital(id="h2", org_id="org_h2", name="Hospital Two", region="South", samples=2000, specialty="Radiology", wallet_address="0x0000000000000000000000000000000000000002"),
        Hospital(id="h3", org_id="org_h3", name="Hospital Three", region="West", samples=1500, specialty="Cardiology", wallet_address="0x0000000000000000000000000000000000000003"),
    ]
    await blockchain.connect()
    for hospital in hospitals:
        if hospital.id != "h3":
            receipt = await blockchain.register_hospital(
                hospital.wallet_address, hospital.org_id, hospital.reputation
            )
            hospital.blockchain_registered = True
            hospital.registry_tx_hash = receipt.registry_tx_hash
            hospital.reputation_tx_hash = receipt.reputation_tx_hash
    for hospital in hospitals:
        await repo.put(
            "organizations",
            Organization(id=hospital.org_id, name=hospital.name, type="hospital", tier="consortium_node"),
        )
        await repo.put("hospitals", hospital)
        await repo.put(
            "users",
            User(
                id=f"usr_{hospital.id}",
                email=f"{hospital.id}@example.com",
                name=f"Node {hospital.id}",
                role="hospital_node",
                org_id=hospital.org_id,
                password_hash=hash_password(TEST_PASSWORD, settings),
            ),
        )

    await repo.put(
        "training_objectives",
        TrainingObjective(
            id="obj_radiology",
            name="Radiology model",
            disease_category="radiology",
            specialty="Radiology",
            min_participants=2,
        ),
    )


def client() -> TestClient:
    settings = Settings(secret_key=TEST_SECRET, digital_twin_path=TWIN_FIXTURE)
    repo = MemoryRepository()
    blockchain = BlockchainService(settings, repo)
    notifications = CapturingNotificationService(settings.frontend_base_url)
    asyncio.run(seed_test_records(repo, settings, blockchain))
    test_client = TestClient(
        create_app(
            settings,
            repository=repo,
            artifact_store=MemoryArtifactStore(),
            blockchain_service=blockchain,
            notification_service=notifications,
        )
    )
    # Expose the repo + captured email to tests that need to inspect them.
    test_client.repo = repo
    test_client.notifications = notifications
    return test_client


def login(
    test_client: TestClient,
    email: str = "admin@example.com",
    password: str = TEST_PASSWORD,
) -> str:
    response = test_client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def valid_update(samples: int, accuracy: float, offset: float = 0) -> dict:
    # Weights separate the twin fixture on feature 0, so they pass the gate.
    return {
        "weights": [4.0 + offset, offset, offset, offset],
        "metrics": {"local_accuracy": accuracy, "loss": 0.1, "samples": samples},
    }


def poisoned_update(samples: int) -> dict:
    return {
        "weights": [-4.0, 0.0, 0.0, 0.0],
        "metrics": {"local_accuracy": 0.9, "loss": 0.1, "samples": samples},
    }


def test_auth_and_protected_dashboard() -> None:
    with client() as test_client:
        assert test_client.get("/dashboard/summary").status_code == 401
        token = login(test_client)
        response = test_client.get("/dashboard/summary", headers=auth(token))
        assert response.status_code == 200
        assert response.json()["hospitals"]


def test_register_via_invitation_creates_persistent_account() -> None:
    with client() as test_client:
        admin_token = login(test_client)
        invite = test_client.post(
            "/auth/invitations",
            json={
                "email": "new.user@clinic.io",
                "role": "clinic_user",
                "new_org": {"name": "Downtown Clinic", "type": "clinic"},
            },
            headers=auth(admin_token),
        )
        assert invite.status_code == 201
        token = invite.json()["invitation"]["token"]
        response = test_client.post(
            "/auth/register",
            json={"token": token, "name": "New Clinic", "password": "supersecret1"},
        )
        assert response.status_code == 201
        assert response.json()["role"] == "clinic_user"
        assert response.json()["refresh_token"]
        assert login(test_client, "new.user@clinic.io", "supersecret1")


def test_register_rejects_reused_invitation() -> None:
    with client() as test_client:
        admin_token = login(test_client)
        invite = test_client.post(
            "/auth/invitations",
            json={
                "email": "second@clinic.io",
                "role": "clinic_user",
                "new_org": {"name": "Second Clinic", "type": "clinic"},
            },
            headers=auth(admin_token),
        )
        token = invite.json()["invitation"]["token"]
        first = test_client.post(
            "/auth/register",
            json={"token": token, "name": "First", "password": "supersecret1"},
        )
        assert first.status_code == 201
        second = test_client.post(
            "/auth/register",
            json={"token": token, "name": "Second", "password": "supersecret1"},
        )
        assert second.status_code == 410


def test_round_aggregates_only_submitted_hospital_updates() -> None:
    with client() as test_client:
        admin_token = login(test_client)
        round_response = test_client.post("/rounds", json={}, headers=auth(admin_token))
        assert round_response.status_code == 200
        training_round = round_response.json()
        assert set(training_round["selected_hospital_ids"]) == {"h1", "h2"}

        updates = {
            "h1": valid_update(1000, 0.8),
            "h2": valid_update(2000, 0.9, 0.1),
        }
        for hospital_id in training_round["selected_hospital_ids"]:
            node_token = login(test_client, f"{hospital_id}@example.com")
            response = test_client.post(
                f"/rounds/{training_round['id']}/submissions",
                json={"hospital_id": hospital_id, "update": updates[hospital_id]},
                headers=auth(node_token),
            )
            assert response.status_code == 200
            assert "weights" not in response.json()

        model = test_client.get("/model-versions/current", headers=auth(admin_token))
        assert model.status_code == 200
        assert model.json()["accuracy"] == 86.67
        assert model.json()["evaluated_accuracy"] == 100.0
        assert model.json()["contributors"] == 2
        assert model.json()["metric_source"] == "digital_twin_evaluation"
        assert len(model.json()["weights"]) == 4
        contributions = test_client.get(
            "/blockchain/contributions", headers=auth(admin_token)
        )
        assert contributions.status_code == 200
        assert len(contributions.json()) == 2
        assert all(item["blockchain_tx_hash"] for item in contributions.json())

        verification = test_client.get("/blockchain/verify", headers=auth(admin_token))
        assert verification.status_code == 200
        assert verification.json()["valid"] is True
        blocks = test_client.get("/blockchain/blocks", headers=auth(admin_token))
        assert blocks.status_code == 200
        recorded = [
            transaction
            for block in blocks.json()
            for transaction in block["transactions"]
            if transaction["type"] == "contribution_recorded"
        ]
        assert len(recorded) == 2

        hospitals = {
            hospital["id"]: hospital
            for hospital in test_client.get("/hospitals", headers=auth(admin_token)).json()
        }
        assert hospitals["h1"]["reputation"] == 82
        assert hospitals["h2"]["reputation"] == 82

        history = test_client.get(
            "/hospitals/h1/reputation/history", headers=auth(admin_token)
        )
        assert history.status_code == 200
        assert history.json()["reputation"] == 82
        assert [item["type"] for item in history.json()["history"]] == [
            "reputation_seeded",
            "reputation_updated",
        ]


def test_digital_twin_gate_rejects_poisoned_update() -> None:
    with client() as test_client:
        admin_token = login(test_client)
        training_round = test_client.post("/rounds", json={}, headers=auth(admin_token)).json()
        assert set(training_round["selected_hospital_ids"]) == {"h1", "h2"}

        good = test_client.post(
            f"/rounds/{training_round['id']}/submissions",
            json={"hospital_id": "h1", "update": valid_update(1000, 0.9)},
            headers=auth(login(test_client, "h1@example.com")),
        )
        assert good.status_code == 200
        assert good.json()["status"] == "verified"

        poisoned = test_client.post(
            f"/rounds/{training_round['id']}/submissions",
            json={"hospital_id": "h2", "update": poisoned_update(2000)},
            headers=auth(login(test_client, "h2@example.com")),
        )
        assert poisoned.status_code == 200
        assert poisoned.json()["status"] == "rejected"
        assert poisoned.json()["evaluated_accuracy"] == 0.0

        completed = test_client.get(
            f"/rounds/{training_round['id']}", headers=auth(admin_token)
        ).json()
        assert completed["status"] == "completed"
        assert completed["contributor_ids"] == ["h1"]
        assert completed["rejected_hospital_ids"] == ["h2"]

        model = test_client.get("/model-versions/current", headers=auth(admin_token)).json()
        assert model["contributors"] == 1
        assert model["evaluated_accuracy"] == 100.0

        hospitals = {
            hospital["id"]: hospital
            for hospital in test_client.get("/hospitals", headers=auth(admin_token)).json()
        }
        assert hospitals["h1"]["reputation"] == 82
        assert hospitals["h2"]["reputation"] == 70

        validations = test_client.get(
            f"/rounds/{training_round['id']}/validations", headers=auth(admin_token)
        ).json()
        failed = [report for report in validations if not report["passed"]]
        assert len(failed) == 1
        assert any("Digital-twin stress test failed" in reason for reason in failed[0]["reasons"])

        blocks = test_client.get("/blockchain/blocks", headers=auth(admin_token)).json()
        recorded = [
            transaction
            for block in blocks
            for transaction in block["transactions"]
            if transaction["type"] == "contribution_recorded"
        ]
        assert len(recorded) == 2
        assert sorted(item["payload"]["validated"] for item in recorded) == [False, True]


def test_submission_rejects_raw_patient_data() -> None:
    with client() as test_client:
        admin_token = login(test_client)
        training_round = test_client.post("/rounds", json={}, headers=auth(admin_token)).json()
        hospital_id = training_round["selected_hospital_ids"][0]
        node_token = login(test_client, f"{hospital_id}@example.com")
        update = valid_update(100, 0.8)
        update["patient_id"] = "forbidden"
        response = test_client.post(
            f"/rounds/{training_round['id']}/submissions",
            json={"hospital_id": hospital_id, "update": update},
            headers=auth(node_token),
        )
        assert response.status_code == 400


def test_hospital_cannot_submit_for_another_organization() -> None:
    with client() as test_client:
        admin_token = login(test_client)
        training_round = test_client.post("/rounds", json={}, headers=auth(admin_token)).json()
        node_token = login(test_client, "h1@example.com")
        response = test_client.post(
            f"/rounds/{training_round['id']}/submissions",
            json={"hospital_id": "h2", "update": valid_update(100, 0.8)},
            headers=auth(node_token),
        )
        assert response.status_code == 403


def test_platform_admin_registers_hospital_wallet_on_chain() -> None:
    with client() as test_client:
        token = login(test_client)
        response = test_client.post(
            "/hospitals/h3/blockchain/register",
            headers=auth(token),
        )
        assert response.status_code == 200
        hospital = response.json()
        assert hospital["blockchain_registered"] is True
        assert hospital["registry_tx_hash"].startswith("0x")
        assert hospital["reputation_tx_hash"].startswith("0x")


def test_removed_fabricated_endpoints_are_not_exposed() -> None:
    with client() as test_client:
        token = login(test_client)
        assert test_client.get("/ledger/events", headers=auth(token)).status_code == 404
        assert test_client.post("/dashboard/reset", headers=auth(token)).status_code == 404


def run_full_round(test_client: TestClient, admin_token: str) -> None:
    training_round = test_client.post("/rounds", json={}, headers=auth(admin_token)).json()
    updates = {"h1": valid_update(1000, 0.8), "h2": valid_update(2000, 0.9, 0.1)}
    for hospital_id in training_round["selected_hospital_ids"]:
        node_token = login(test_client, f"{hospital_id}@example.com")
        response = test_client.post(
            f"/rounds/{training_round['id']}/submissions",
            json={"hospital_id": hospital_id, "update": updates[hospital_id]},
            headers=auth(node_token),
        )
        assert response.status_code == 200


def test_admin_can_cancel_a_stuck_round() -> None:
    with client() as test_client:
        admin_token = login(test_client)
        training_round = test_client.post("/rounds", json={}, headers=auth(admin_token)).json()
        blocked = test_client.post("/rounds", json={}, headers=auth(admin_token))
        assert blocked.status_code == 409

        cancelled = test_client.post(
            f"/rounds/{training_round['id']}/cancel", headers=auth(admin_token)
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "failed"

        next_round = test_client.post("/rounds", json={}, headers=auth(admin_token))
        assert next_round.status_code == 200

        already_done = test_client.post(
            f"/rounds/{training_round['id']}/cancel", headers=auth(admin_token)
        )
        assert already_done.status_code == 409


def test_inference_requires_an_aggregated_model() -> None:
    with client() as test_client:
        token = login(test_client)
        response = test_client.post(
            "/inference/predict", json={"features": [3.0, 0.0, 0.0]}, headers=auth(token)
        )
        assert response.status_code == 409


def test_inference_predicts_from_real_global_weights() -> None:
    with client() as test_client:
        admin_token = login(test_client)
        run_full_round(test_client, admin_token)

        confident = test_client.post(
            "/inference/predict", json={"features": [3.0, 0.0, 0.0]}, headers=auth(admin_token)
        )
        assert confident.status_code == 200
        payload = confident.json()
        assert payload["prediction"] == "benign"
        assert payload["confidence"] > 0.99
        assert payload["confidence_tier"] == "high"
        assert payload["specialist_consultation_recommended"] is False
        assert payload["model_version"] == "v1"

        uncertain = test_client.post(
            "/inference/predict", json={"features": [0.01, 0.0, 0.0]}, headers=auth(admin_token)
        )
        assert uncertain.status_code == 200
        assert uncertain.json()["confidence_tier"] == "low"
        assert uncertain.json()["specialist_consultation_recommended"] is True

        wrong_count = test_client.post(
            "/inference/predict", json={"features": [1.0]}, headers=auth(admin_token)
        )
        assert wrong_count.status_code == 400

        node_token = login(test_client, "h1@example.com")
        forbidden = test_client.post(
            "/inference/predict", json={"features": [3.0, 0.0, 0.0]}, headers=auth(node_token)
        )
        assert forbidden.status_code == 403

        invite = test_client.post(
            "/auth/invitations",
            json={
                "email": "clinic@example.com",
                "role": "clinic_user",
                "new_org": {"name": "Downtown Clinic", "type": "clinic"},
            },
            headers=auth(admin_token),
        )
        assert invite.status_code == 201
        registered = test_client.post(
            "/auth/register",
            json={
                "token": invite.json()["invitation"]["token"],
                "name": "Clinic User",
                "password": "supersecret1",
            },
        )
        assert registered.status_code == 201
        clinic_token = registered.json()["access_token"]
        clinic_response = test_client.post(
            "/inference/predict", json={"features": [3.0, 0.0, 0.0]}, headers=auth(clinic_token)
        )
        assert clinic_response.status_code == 200
