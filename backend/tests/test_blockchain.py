from __future__ import annotations

import asyncio

import pytest

from backend.app.config import Settings
from backend.app.services.blockchain import CHAIN_COLLECTION, BlockchainService
from backend.tests.fakes import MemoryRepository

TEST_SECRET = "test-secret-key-that-is-longer-than-thirty-two-characters"
WALLET_A = "0x00000000000000000000000000000000000000a1"
WALLET_B = "0x00000000000000000000000000000000000000b2"
UPDATE_HASH = "0x" + "ab" * 32


def settings() -> Settings:
    return Settings(secret_key=TEST_SECRET)


def test_connect_creates_verified_genesis() -> None:
    async def scenario() -> None:
        service = BlockchainService(settings(), MemoryRepository())
        await service.connect()
        assert service.connected
        assert service.height == 0
        assert service.signer_address and service.signer_address.startswith("0x")
        report = service.verify()
        assert report["valid"] is True
        assert report["blocks"] == 1
        assert report["authority"] == service.signer_address

    asyncio.run(scenario())


def test_registration_and_contribution_lifecycle() -> None:
    async def scenario() -> None:
        repo = MemoryRepository()
        service = BlockchainService(settings(), repo)
        await service.connect()

        receipt = await service.register_hospital(WALLET_A, "org_a", 80)
        assert receipt.registry_tx_hash and receipt.reputation_tx_hash

        contribution = await service.record_contribution(
            round_id="rnd_1",
            model_version="v1",
            contributor=WALLET_A,
            update_hash=UPDATE_HASH,
            artifact_uri="azure://updates/example.json",
            validated=True,
        )
        assert contribution.tx_hash.startswith("0x")
        assert contribution.block_number == service.height

        with pytest.raises(RuntimeError, match="already recorded"):
            await service.record_contribution(
                round_id="rnd_1",
                model_version="v1",
                contributor=WALLET_A,
                update_hash=UPDATE_HASH,
                artifact_uri="azure://updates/example.json",
                validated=True,
            )

        # Wallets are bound to a single organization, as in the Solidity registry.
        with pytest.raises(RuntimeError, match="different organization"):
            await service.register_hospital(WALLET_A, "org_other", 50)

        # Re-registering the same wallet/org mints no new registry transaction.
        repeat = await service.register_hospital(WALLET_A, "org_a", 80)
        assert repeat.registry_tx_hash is None
        assert repeat.reputation_tx_hash is None

        # A fresh service over the same storage replays identical state.
        reloaded = BlockchainService(settings(), repo)
        await reloaded.connect()
        assert reloaded.height == service.height
        with pytest.raises(RuntimeError, match="already recorded"):
            await reloaded.record_contribution(
                round_id="rnd_1",
                model_version="v1",
                contributor=WALLET_A,
                update_hash=UPDATE_HASH,
                artifact_uri="azure://updates/example.json",
                validated=True,
            )

    asyncio.run(scenario())


def test_reputation_updates_clamp_and_persist() -> None:
    async def scenario() -> None:
        repo = MemoryRepository()
        service = BlockchainService(settings(), repo)
        await service.connect()
        await service.register_hospital(WALLET_A, "org_a", 80)

        receipt, score = await service.update_reputation(WALLET_A, 2, "verified_contribution", "rnd_1")
        assert receipt is not None and score == 82

        receipt, score = await service.update_reputation(WALLET_A, 50, "verified_contribution", "rnd_2")
        assert receipt is not None and score == 100

        receipt, score = await service.update_reputation(WALLET_A, 2, "verified_contribution", "rnd_3")
        assert receipt is None and score == 100

        receipt, score = await service.update_reputation(WALLET_A, -10, "rejected_contribution", "rnd_4")
        assert receipt is not None and score == 90

        with pytest.raises(RuntimeError, match="not an active consortium node"):
            await service.update_reputation(WALLET_B, 2, "verified_contribution", "rnd_1")

        reloaded = BlockchainService(settings(), repo)
        await reloaded.connect()
        history = reloaded.reputation_history(WALLET_A)
        assert [item["type"] for item in history] == [
            "reputation_seeded",
            "reputation_updated",
            "reputation_updated",
            "reputation_updated",
        ]
        assert history[-1]["score"] == 90

    asyncio.run(scenario())


def test_rejects_unregistered_contributor() -> None:
    async def scenario() -> None:
        service = BlockchainService(settings(), MemoryRepository())
        await service.connect()
        with pytest.raises(RuntimeError, match="not an active consortium node"):
            await service.record_contribution(
                round_id="rnd_1",
                model_version="v1",
                contributor=WALLET_B,
                update_hash=UPDATE_HASH,
                artifact_uri="azure://updates/example.json",
                validated=True,
            )

    asyncio.run(scenario())


def test_tampered_history_is_detected_on_startup() -> None:
    async def scenario() -> None:
        repo = MemoryRepository()
        service = BlockchainService(settings(), repo)
        await service.connect()
        await service.register_hospital(WALLET_A, "org_a", 80)

        stored_blocks = repo._collections[CHAIN_COLLECTION]
        tampered = stored_blocks[f"blk_{1:012d}"]
        tampered.transactions[-1].payload["score"] = 100

        reloaded = BlockchainService(settings(), repo)
        with pytest.raises(RuntimeError, match="altered after signing"):
            await reloaded.connect()

    asyncio.run(scenario())


def test_chain_from_other_authority_is_rejected() -> None:
    async def scenario() -> None:
        repo = MemoryRepository()
        service = BlockchainService(settings(), repo)
        await service.connect()

        other = BlockchainService(
            Settings(secret_key="another-secret-key-that-is-also-long-enough-000"), repo
        )
        with pytest.raises(RuntimeError, match="different authority key"):
            await other.connect()

    asyncio.run(scenario())
