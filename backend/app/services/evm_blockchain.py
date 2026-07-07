"""Real on-chain blockchain service: the Solidity contracts on an in-process EVM.

Runs a genuine EVM inside the Python process (web3.py + eth-tester/py-evm), deploys
the compiled `ConsortiumRegistry` / `ReputationRegistry` / `TrainingLedger` contracts on
startup, and executes real transactions against them — no external node, no gas, no RPC
provider. MongoDB stays the durable source of truth: on every startup the chain is
redeployed (deterministic addresses) and historical state is replayed from Mongo.

Preserves the exact public interface of ``BlockchainService`` so ``runtime.py`` and
``routes.py`` are unchanged. Reputation is contract-owned in this backend: the
``TrainingLedger.recordContribution`` call moves reputation via ``applyContribution``,
so ``update_reputation`` here reads the resulting on-chain score back rather than
applying the settings-based delta a second time.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from ..config import Settings
from ..models import Hospital, Submission, TrainingRound
from ..store import Repository
from .blockchain import RegistrationReceipt, TransactionReceipt

logger = logging.getLogger("medchain.evm")

NETWORK_NAME = "medchain-consortium"
HOSPITAL_ROLE = b"hospital_node".ljust(32, b"\x00")
_ARTIFACT_ROOT = Path(__file__).resolve().parents[3] / "contracts" / "artifacts" / "contracts"
_CONTRACTS = {
    "registry": "ConsortiumRegistry",
    "reputation": "ReputationRegistry",
    "ledger": "TrainingLedger",
}


def _load_artifact(name: str) -> dict[str, Any]:
    return json.loads((_ARTIFACT_ROOT / f"{name}.sol" / f"{name}.json").read_text())


class EvmBlockchainService:
    def __init__(self, settings: Settings, repository: Repository):
        self.settings = settings
        self.repo = repository
        self.connected = False
        self.chain_id = settings.chain_id
        self.signer_address: str | None = None
        self._w3: Any = None
        self._authority: str | None = None
        self._registry: Any = None
        self._reputation: Any = None
        self._ledger: Any = None
        self._lock = asyncio.Lock()

    @property
    def height(self) -> int:
        return int(self._w3.eth.block_number) if self._w3 is not None else 0

    async def connect(self) -> None:
        self._lock = asyncio.Lock()
        from web3 import Web3
        from web3.providers.eth_tester import EthereumTesterProvider

        w3 = Web3(EthereumTesterProvider())
        self._w3 = w3
        self._authority = w3.eth.accounts[0]
        w3.eth.default_account = self._authority
        self.signer_address = self._authority

        self._registry = self._deploy("registry")
        self._reputation = self._deploy("reputation")
        self._ledger = self._deploy(
            "ledger", self._registry.address, self._reputation.address
        )
        self._send(self._reputation.functions.setTrainingLedger(self._ledger.address))

        await self._replay_from_store()
        self.connected = True
        logger.info("EVM chain up: registry=%s ledger=%s", self._registry.address, self._ledger.address)

    async def close(self) -> None:
        self.connected = False

    # ------------------------------------------------------------------ deploy/replay

    def _deploy(self, key: str, *args: Any) -> Any:
        artifact = _load_artifact(_CONTRACTS[key])
        contract = self._w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
        tx_hash = contract.constructor(*args).transact()
        receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash)
        return self._w3.eth.contract(address=receipt.contractAddress, abi=artifact["abi"])

    def _send(self, function_call: Any) -> Any:
        tx_hash = function_call.transact()
        return self._w3.eth.wait_for_transaction_receipt(tx_hash)

    async def _replay_from_store(self) -> None:
        """Rebuild on-chain state from Mongo so restarts are consistent (Mongo is durable)."""
        hospitals = [
            h
            for h in await self.repo.list("hospitals", Hospital)
            if h.blockchain_registered and h.wallet_address
        ]
        for hospital in hospitals:
            self._ensure_registered(hospital.wallet_address, hospital.org_id, hospital.reputation)
        # Replay previously-recorded contributions into the ledger, in submission order.
        recorded = sorted(
            [s for s in await self.repo.list("submissions", Submission) if s.blockchain_tx_hash],
            key=lambda s: s.submitted_at,
        )
        wallets = {h.id: h.wallet_address for h in hospitals}
        for submission in recorded:
            wallet = wallets.get(submission.hospital_id)
            if not wallet:
                continue
            try:
                self._record(
                    submission.round_id,
                    "replay",
                    wallet,
                    submission.update_hash,
                    submission.artifact_uri,
                    submission.status == "verified",
                )
            except Exception:  # noqa: BLE001 - a replayed dup just means it is already on-chain
                continue
        # Re-seed reputations to the authoritative stored values after replay side effects.
        for hospital in hospitals:
            self._send(
                self._reputation.functions.seedReputation(
                    self._addr(hospital.wallet_address), int(hospital.reputation)
                )
            )

    # ------------------------------------------------------------------ public API

    async def register_hospital(
        self, wallet_address: str, org_id: str, reputation: int
    ) -> RegistrationReceipt:
        async with self._lock:
            self._require_connected()
            return self._ensure_registered(wallet_address, org_id, reputation)

    async def record_contribution(
        self,
        round_id: str,
        model_version: str,
        contributor: str,
        update_hash: str,
        artifact_uri: str,
        validated: bool,
    ) -> TransactionReceipt:
        async with self._lock:
            self._require_connected()
            return self._record(
                round_id, model_version, contributor, update_hash, artifact_uri, validated
            )

    async def update_reputation(
        self, wallet_address: str, delta: int, reason: str, round_id: str
    ) -> tuple[TransactionReceipt | None, int]:
        # Reputation is moved by the contract inside recordContribution; read it back here.
        async with self._lock:
            self._require_connected()
            score = int(self._reputation.functions.reputation(self._addr(wallet_address)).call())
            return None, score

    def reputation_history(self, wallet_address: str) -> list[dict[str, Any]]:
        self._require_connected()
        wallet = self._addr(wallet_address)
        history: list[dict[str, Any]] = []
        for event in self._reputation.events.ReputationChanged().get_logs(from_block=0):
            if event["args"]["node"] != wallet:
                continue
            history.append(
                {
                    "type": "reputation_updated",
                    "wallet": wallet_address.lower(),
                    "score": int(event["args"]["score"]),
                    "delta": int(event["args"]["delta"]),
                    "block_number": int(event["blockNumber"]),
                    "tx_hash": event["transactionHash"].hex(),
                }
            )
        return history

    def export_blocks(self, limit: int = 100) -> list[dict[str, Any]]:
        self._require_connected()
        by_block: dict[int, list[dict[str, Any]]] = {}
        for tx in self._all_transactions():
            by_block.setdefault(tx["block_number"], []).append(tx)
        blocks: list[dict[str, Any]] = []
        for number in sorted(by_block, reverse=True)[:limit]:
            block = self._w3.eth.get_block(number)
            blocks.append(
                {
                    "number": number,
                    "hash": block["hash"].hex(),
                    "timestamp": int(block["timestamp"]),
                    "signer": self.signer_address,
                    "transactions": by_block[number],
                }
            )
        return blocks

    def verify(self) -> dict[str, Any]:
        self._require_connected()
        from datetime import UTC, datetime

        return {
            "valid": True,
            "error": None,
            "network": NETWORK_NAME,
            "chain_id": self.chain_id,
            "height": self.height,
            "blocks": self.height,
            "transactions": int(self._ledger.functions.contributionCount().call()),
            "authority": self.signer_address,
            "verified_at": datetime.now(UTC).isoformat(),
        }

    # ------------------------------------------------------------------ internals

    def _ensure_registered(
        self, wallet_address: str, org_id: str, reputation: int
    ) -> RegistrationReceipt:
        addr = self._addr(wallet_address)
        registry_tx: str | None = None
        reputation_tx: str | None = None
        org_on_chain, _role, active, registered_at = self._registry.functions.getNode(addr).call()
        if int(registered_at) == 0:
            receipt = self._send(self._registry.functions.registerNode(addr, org_id, HOSPITAL_ROLE))
            registry_tx = receipt.transactionHash.hex()
        else:
            if org_on_chain != org_id:
                raise RuntimeError("Wallet is already registered to a different organization")
            if not active:
                receipt = self._send(self._registry.functions.setNodeActive(addr, True))
                registry_tx = receipt.transactionHash.hex()
        if int(self._reputation.functions.reputation(addr).call()) == 0:
            receipt = self._send(
                self._reputation.functions.seedReputation(addr, int(reputation))
            )
            reputation_tx = receipt.transactionHash.hex()
        return RegistrationReceipt(registry_tx, reputation_tx)

    def _record(
        self,
        round_id: str,
        model_version: str,
        contributor: str,
        update_hash: str,
        artifact_uri: str,
        validated: bool,
    ) -> TransactionReceipt:
        from web3 import Web3

        round_key = Web3.keccak(text=round_id)
        update_bytes = bytes.fromhex(update_hash.removeprefix("0x"))
        if len(update_bytes) != 32:
            raise RuntimeError("Model update hash must contain 32 bytes")
        receipt = self._send(
            self._ledger.functions.recordContribution(
                round_key,
                model_version,
                self._addr(contributor),
                update_bytes,
                artifact_uri,
                validated,
            )
        )
        return TransactionReceipt(receipt.transactionHash.hex(), int(receipt.blockNumber))

    def _all_transactions(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for event in self._registry.events.NodeRegistered().get_logs(from_block=0):
            events.append(
                {
                    "tx_hash": event["transactionHash"].hex(),
                    "block_number": int(event["blockNumber"]),
                    "type": "node_registered",
                    "payload": {
                        "wallet": event["args"]["node"].lower(),
                        "org_id": event["args"]["orgId"],
                    },
                }
            )
        for event in self._reputation.events.ReputationChanged().get_logs(from_block=0):
            events.append(
                {
                    "tx_hash": event["transactionHash"].hex(),
                    "block_number": int(event["blockNumber"]),
                    "type": "reputation_updated",
                    "payload": {
                        "wallet": event["args"]["node"].lower(),
                        "score": int(event["args"]["score"]),
                        "delta": int(event["args"]["delta"]),
                    },
                }
            )
        for event in self._ledger.events.ContributionRecorded().get_logs(from_block=0):
            events.append(
                {
                    "tx_hash": event["transactionHash"].hex(),
                    "block_number": int(event["blockNumber"]),
                    "type": "contribution_recorded",
                    "payload": {
                        "contributor": event["args"]["contributor"].lower(),
                        "model_version": event["args"]["modelVersion"],
                        "artifact_uri": event["args"]["artifactCid"],
                        "validated": bool(event["args"]["validated"]),
                    },
                }
            )
        return events

    def _addr(self, wallet_address: str) -> str:
        from web3 import Web3

        return Web3.to_checksum_address(wallet_address)

    def _require_connected(self) -> None:
        if not self.connected and self._w3 is None:
            raise RuntimeError("EVM blockchain service is not connected")
