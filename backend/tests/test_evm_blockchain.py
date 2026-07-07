from __future__ import annotations

import asyncio

from backend.app.config import Settings
from backend.app.models import Hospital, Submission
from backend.app.services.evm_blockchain import EvmBlockchainService
from backend.tests.fakes import MemoryRepository

TEST_SECRET = "test-secret-key-that-is-longer-than-thirty-two-characters"
WALLET = "0x" + "11" * 20
UPDATE_HASH = "0x" + "ab" * 32


def _settings() -> Settings:
    return Settings(secret_key=TEST_SECRET)


def test_evm_chain_registers_records_and_moves_reputation() -> None:
    svc = EvmBlockchainService(_settings(), MemoryRepository())

    async def run() -> None:
        await svc.connect()
        assert svc.connected
        assert svc.signer_address

        reg = await svc.register_hospital(WALLET, "org_h1", 92)
        assert reg.registry_tx_hash and reg.reputation_tx_hash

        receipt = await svc.record_contribution(
            "rnd_1", "v1", WALLET, UPDATE_HASH, "memory://update", True
        )
        assert receipt.block_number > 0

        # Contract moved reputation via applyContribution (+1 for a verified update).
        _, score = await svc.update_reputation(WALLET, 2, "verified_contribution", "rnd_1")
        assert score == 93

        history = svc.reputation_history(WALLET)
        assert any(item["type"] == "reputation_updated" for item in history)

        blocks = svc.export_blocks()
        assert blocks and any(tx["type"] == "contribution_recorded" for tx in blocks[0]["transactions"])

        report = svc.verify()
        assert report["valid"] is True
        assert report["transactions"] >= 1
        await svc.close()

    asyncio.run(run())


def test_evm_chain_rejects_duplicate_contribution() -> None:
    svc = EvmBlockchainService(_settings(), MemoryRepository())

    async def run() -> None:
        await svc.connect()
        await svc.register_hospital(WALLET, "org_h1", 80)
        await svc.record_contribution("rnd_1", "v1", WALLET, UPDATE_HASH, "memory://u", True)
        try:
            await svc.record_contribution("rnd_1", "v1", WALLET, UPDATE_HASH, "memory://u", True)
        except Exception:
            return
        raise AssertionError("duplicate contribution should have reverted")

    asyncio.run(run())


def test_evm_chain_replays_state_from_store() -> None:
    repo = MemoryRepository()

    async def seed() -> None:
        await repo.put(
            "hospitals",
            Hospital(
                id="h1",
                org_id="org_h1",
                name="H1",
                region="North",
                samples=1000,
                specialty="Radiology",
                reputation=88,
                wallet_address=WALLET,
                blockchain_registered=True,
            ),
        )
        await repo.put(
            "submissions",
            Submission(
                round_id="rnd_prev",
                hospital_id="h1",
                artifact_uri="memory://prev",
                update_hash=UPDATE_HASH,
                weights=[1.0],
                status="verified",
                blockchain_tx_hash="0xdead",
            ),
        )

    asyncio.run(seed())
    svc = EvmBlockchainService(_settings(), repo)

    async def run() -> None:
        await svc.connect()
        # Node is registered and reputation matches the stored (authoritative) value.
        _, score = await svc.update_reputation(WALLET, 0, "read", "rnd_prev")
        assert score == 88
        # The replayed contribution is present in the ledger.
        assert svc.verify()["transactions"] >= 1
        await svc.close()

    asyncio.run(run())
