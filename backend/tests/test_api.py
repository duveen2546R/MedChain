from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Hospital, Organization, TrainingObjective, User
from backend.app.security import hash_password
from backend.tests.fakes import MemoryArtifactStore, MemoryBlockchainService, MemoryRepository

TEST_SECRET = "test-secret-key-that-is-longer-than-thirty-two-characters"
TEST_PASSWORD = "test-password-123"


async def seed_test_records(repo: MemoryRepository, settings: Settings) -> None:
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
        Hospital(id="h1", org_id="org_h1", name="Hospital One", region="North", samples=1000, specialty="Radiology", wallet_address="0x0000000000000000000000000000000000000001", blockchain_registered=True),
        Hospital(id="h2", org_id="org_h2", name="Hospital Two", region="South", samples=2000, specialty="Radiology", wallet_address="0x0000000000000000000000000000000000000002", blockchain_registered=True),
        Hospital(id="h3", org_id="org_h3", name="Hospital Three", region="West", samples=1500, specialty="Cardiology", wallet_address="0x0000000000000000000000000000000000000003", blockchain_registered=False),
    ]
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
    settings = Settings(secret_key=TEST_SECRET)
    repo = MemoryRepository()
    asyncio.run(seed_test_records(repo, settings))
    return TestClient(
        create_app(
            settings,
            repository=repo,
            artifact_store=MemoryArtifactStore(),
            blockchain_service=MemoryBlockchainService(),
        )
    )


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
    return {
        "weights": [0.1 + offset, 0.2 + offset, 0.3 + offset],
        "metrics": {"local_accuracy": accuracy, "loss": 0.1, "samples": samples},
    }


def test_auth_and_protected_dashboard() -> None:
    with client() as test_client:
        assert test_client.get("/dashboard/summary").status_code == 401
        token = login(test_client)
        response = test_client.get("/dashboard/summary", headers=auth(token))
        assert response.status_code == 200
        assert response.json()["hospitals"]


def test_register_creates_persistent_account() -> None:
    with client() as test_client:
        response = test_client.post(
            "/auth/register",
            json={
                "name": "New Clinic",
                "email": "new.user@clinic.io",
                "password": "supersecret1",
                "organization": "Downtown Clinic",
                "account_type": "clinic",
            },
        )
        assert response.status_code == 201
        assert response.json()["role"] == "clinic_user"
        assert login(test_client, "new.user@clinic.io", "supersecret1")


def test_register_rejects_duplicate_email() -> None:
    with client() as test_client:
        response = test_client.post(
            "/auth/register",
            json={
                "name": "Duplicate",
                "email": "admin@example.com",
                "password": "supersecret1",
                "organization": "Duplicate Org",
                "account_type": "hospital",
            },
        )
        assert response.status_code == 409


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
        assert model.json()["contributors"] == 2
        assert model.json()["metric_source"] == "weighted_client_report"
        contributions = test_client.get(
            "/blockchain/contributions", headers=auth(admin_token)
        )
        assert contributions.status_code == 200
        assert len(contributions.json()) == 2
        assert all(item["blockchain_tx_hash"] for item in contributions.json())


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
        assert test_client.post("/inference/predict", json={}, headers=auth(token)).status_code == 404
        assert test_client.get("/ledger/events", headers=auth(token)).status_code == 404
        assert test_client.post("/dashboard/reset", headers=auth(token)).status_code == 404
