"""End-to-end: the app running a real training round on the in-process EVM backend
(chain_backend='evm', no injected blockchain), exercising the runtime ↔ contracts seam."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Hospital, Organization, TrainingObjective, User
from backend.app.security import hash_password
from backend.tests.fakes import CapturingNotificationService, MemoryArtifactStore, MemoryRepository
from backend.tests.test_api import TEST_PASSWORD, TEST_SECRET, TWIN_FIXTURE, auth, valid_update


async def _seed(repo: MemoryRepository, settings: Settings) -> None:
    await repo.put("organizations", Organization(id="org_platform", name="Platform", type="platform", tier="internal"))
    await repo.put(
        "users",
        User(id="usr_admin", email="admin@example.com", name="Admin", role="platform_admin",
             org_id="org_platform", password_hash=hash_password(TEST_PASSWORD, settings)),
    )
    for index, hid in enumerate(("h1", "h2"), start=1):
        await repo.put("organizations", Organization(id=f"org_{hid}", name=hid, type="hospital", tier="consortium_node"))
        await repo.put(
            "hospitals",
            Hospital(id=hid, org_id=f"org_{hid}", name=hid, region="North", samples=1000,
                     specialty="Radiology", reputation=80, wallet_address=f"0x{index:040x}",
                     blockchain_registered=True),  # EVM replay registers these on connect
        )
        await repo.put(
            "users",
            User(id=f"usr_{hid}", email=f"{hid}@example.com", name=hid, role="hospital_node",
                 org_id=f"org_{hid}", password_hash=hash_password(TEST_PASSWORD, settings)),
        )
    await repo.put(
        "training_objectives",
        TrainingObjective(id="obj_rad", name="Radiology", disease_category="rad",
                          specialty="Radiology", min_participants=2),
    )


def test_full_round_runs_on_the_evm_backend() -> None:
    settings = Settings(secret_key=TEST_SECRET, digital_twin_path=TWIN_FIXTURE, chain_backend="evm")
    repo = MemoryRepository()
    asyncio.run(_seed(repo, settings))
    app = create_app(
        settings,
        repository=repo,
        artifact_store=MemoryArtifactStore(),
        notification_service=CapturingNotificationService(),
        # no blockchain_service → runtime builds the EVM service from chain_backend="evm"
    )
    with TestClient(app) as tc:
        health = tc.get("/health").json()
        assert health["blockchain_connected"] is True

        token = tc.post("/auth/login", json={"email": "admin@example.com", "password": TEST_PASSWORD}).json()["access_token"]
        training_round = tc.post("/rounds", json={}, headers=auth(token)).json()
        updates = {"h1": valid_update(1000, 0.8), "h2": valid_update(2000, 0.9, 0.1)}
        for hid in training_round["selected_hospital_ids"]:
            node = tc.post("/auth/login", json={"email": f"{hid}@example.com", "password": TEST_PASSWORD}).json()["access_token"]
            resp = tc.post(f"/rounds/{training_round['id']}/submissions",
                           json={"hospital_id": hid, "update": updates[hid]}, headers=auth(node))
            assert resp.status_code == 200

        final = tc.get(f"/rounds/{training_round['id']}", headers=auth(token)).json()
        assert final["status"] == "completed"

        verify = tc.get("/blockchain/verify", headers=auth(token)).json()
        assert verify["valid"] is True
        assert verify["transactions"] >= 2  # two contributions recorded on-chain

        # Contributions are recorded on-chain with real tx hashes + block numbers.
        contributions = tc.get("/blockchain/contributions", headers=auth(token)).json()
        assert contributions and all(c["blockchain_tx_hash"] for c in contributions)
