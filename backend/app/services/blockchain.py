from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from eth_account import Account
from eth_account.messages import encode_defunct
from pydantic import BaseModel, Field

from ..config import Settings
from ..store import Repository

CHAIN_COLLECTION = "blockchain_blocks"
GENESIS_PREVIOUS_HASH = "0x" + "0" * 64
HOSPITAL_ROLE = "hospital_node"
NETWORK_NAME = "medchain-consortium"

TransactionType = Literal[
    "genesis",
    "node_registered",
    "node_activated",
    "reputation_seeded",
    "reputation_updated",
    "contribution_recorded",
]


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _canonical(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _sha256_hex(data: bytes) -> str:
    return "0x" + hashlib.sha256(data).hexdigest()


def _as_0x_hex(value: Any) -> str:
    text = value if isinstance(value, str) else value.hex()
    return text if text.startswith("0x") else f"0x{text}"


def _merkle_root(tx_hashes: list[str]) -> str:
    if not tx_hashes:
        return _sha256_hex(b"")
    layer = [bytes.fromhex(tx_hash.removeprefix("0x")) for tx_hash in tx_hashes]
    while len(layer) > 1:
        if len(layer) % 2:
            layer.append(layer[-1])
        layer = [
            hashlib.sha256(layer[index] + layer[index + 1]).digest()
            for index in range(0, len(layer), 2)
        ]
    return "0x" + layer[0].hex()


class ChainTransaction(BaseModel):
    tx_hash: str
    type: TransactionType
    payload: dict[str, Any]
    timestamp: str
    signer: str
    signature: str

    def content_hash(self) -> str:
        return _sha256_hex(
            _canonical(
                {
                    "type": self.type,
                    "payload": self.payload,
                    "timestamp": self.timestamp,
                    "signer": self.signer,
                }
            )
        )


class Block(BaseModel):
    id: str
    chain_id: int
    number: int
    timestamp: str
    previous_hash: str
    merkle_root: str
    transactions: list[ChainTransaction] = Field(default_factory=list)
    hash: str
    signer: str
    signature: str

    def header_hash(self) -> str:
        return _sha256_hex(
            _canonical(
                {
                    "chain_id": self.chain_id,
                    "number": self.number,
                    "timestamp": self.timestamp,
                    "previous_hash": self.previous_hash,
                    "merkle_root": self.merkle_root,
                }
            )
        )


@dataclass(frozen=True)
class TransactionReceipt:
    tx_hash: str
    block_number: int


@dataclass(frozen=True)
class RegistrationReceipt:
    registry_tx_hash: str | None
    reputation_tx_hash: str | None


@dataclass
class NodeRecord:
    org_id: str
    role: str
    active: bool
    registered_at: str


class BlockchainService:
    """Embedded consortium blockchain: hash-linked, ECDSA-signed blocks in MongoDB.

    The service is the consortium authority node. Every registration, reputation
    seed, and training contribution becomes a signed transaction inside a block
    whose header commits to the previous block hash and the merkle root of its
    transactions, so any modification of stored history is detected on startup.
    Only metadata and content hashes go on-chain; model weights stay off-chain.
    """

    def __init__(self, settings: Settings, repository: Repository):
        self.settings = settings
        self.repo = repository
        self.connected = False
        self.chain_id = settings.chain_id
        self.signer_address: str | None = None
        self._account: Any = None
        self._blocks: list[Block] = []
        self._nodes: dict[str, NodeRecord] = {}
        self._reputation: dict[str, int] = {}
        self._contributions: set[tuple[str, str]] = set()
        self._lock = asyncio.Lock()

    @property
    def height(self) -> int:
        return self._blocks[-1].number if self._blocks else 0

    async def connect(self) -> None:
        # Recreated here so the lock binds to the event loop that runs the app.
        self._lock = asyncio.Lock()
        self._account = Account.from_key(self._authority_key())
        self.signer_address = self._account.address

        blocks = await self.repo.list(CHAIN_COLLECTION, Block)
        blocks.sort(key=lambda block: block.number)
        if blocks:
            self._verify_blocks(blocks)
            if blocks[0].signer != self.signer_address:
                raise RuntimeError(
                    "The stored consortium chain was created by a different authority key. "
                    "Keep MEDCHAIN_SIGNER_PRIVATE_KEY (or MEDCHAIN_SECRET_KEY) stable, or "
                    f"clear the '{CHAIN_COLLECTION}' collection to start a new chain."
                )
            self._blocks = blocks
            self._replay_state()
        else:
            self._blocks = []
            self._nodes = {}
            self._reputation = {}
            self._contributions = set()
            genesis_tx = self._make_transaction(
                "genesis",
                {"network": NETWORK_NAME, "chain_id": self.chain_id},
            )
            await self._append_block([genesis_tx])
        self.connected = True

    async def close(self) -> None:
        self.connected = False

    async def register_hospital(
        self,
        wallet_address: str,
        org_id: str,
        reputation: int,
    ) -> RegistrationReceipt:
        async with self._lock:
            self._require_connected()
            wallet = self._normalize_wallet(wallet_address)
            transactions: list[ChainTransaction] = []
            registry_tx: ChainTransaction | None = None
            reputation_tx: ChainTransaction | None = None

            node = self._nodes.get(wallet)
            if node is not None:
                if node.org_id != org_id:
                    raise RuntimeError("Wallet is already registered to a different organization")
                if not node.active:
                    registry_tx = self._make_transaction(
                        "node_activated", {"wallet": wallet, "active": True}
                    )
                    transactions.append(registry_tx)
            else:
                registry_tx = self._make_transaction(
                    "node_registered",
                    {"wallet": wallet, "org_id": org_id, "role": HOSPITAL_ROLE},
                )
                transactions.append(registry_tx)

            if self._reputation.get(wallet, 0) == 0:
                reputation_tx = self._make_transaction(
                    "reputation_seeded", {"wallet": wallet, "score": reputation}
                )
                transactions.append(reputation_tx)

            if transactions:
                await self._append_block(transactions)
            return RegistrationReceipt(
                registry_tx.tx_hash if registry_tx else None,
                reputation_tx.tx_hash if reputation_tx else None,
            )

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
            wallet = self._normalize_wallet(contributor)
            update_hash_bytes = bytes.fromhex(update_hash.removeprefix("0x"))
            if len(update_hash_bytes) != 32:
                raise RuntimeError("Model update hash must contain 32 bytes")

            node = self._nodes.get(wallet)
            if node is None or not node.active:
                raise RuntimeError("Contributor wallet is not an active consortium node")

            round_hash = _sha256_hex(round_id.encode())
            if (round_hash, wallet) in self._contributions:
                raise RuntimeError("Contribution is already recorded on-chain")

            transaction = self._make_transaction(
                "contribution_recorded",
                {
                    "round_id": round_id,
                    "round_hash": round_hash,
                    "model_version": model_version,
                    "contributor": wallet,
                    "update_hash": _as_0x_hex(update_hash_bytes.hex()),
                    "artifact_uri": artifact_uri,
                    "validated": validated,
                },
            )
            block = await self._append_block([transaction])
            return TransactionReceipt(transaction.tx_hash, block.number)

    async def update_reputation(
        self,
        wallet_address: str,
        delta: int,
        reason: str,
        round_id: str,
    ) -> tuple[TransactionReceipt | None, int]:
        async with self._lock:
            self._require_connected()
            wallet = self._normalize_wallet(wallet_address)
            node = self._nodes.get(wallet)
            if node is None or not node.active:
                raise RuntimeError("Wallet is not an active consortium node")
            previous = self._reputation.get(wallet, 0)
            score = max(0, min(100, previous + delta))
            if score == previous:
                return None, previous
            transaction = self._make_transaction(
                "reputation_updated",
                {
                    "wallet": wallet,
                    "previous": previous,
                    "delta": score - previous,
                    "score": score,
                    "reason": reason,
                    "round_id": round_id,
                },
            )
            block = await self._append_block([transaction])
            return TransactionReceipt(transaction.tx_hash, block.number), score

    def reputation_history(self, wallet_address: str) -> list[dict[str, Any]]:
        self._require_connected()
        wallet = self._normalize_wallet(wallet_address)
        history: list[dict[str, Any]] = []
        for block in self._blocks:
            for transaction in block.transactions:
                if (
                    transaction.type in {"reputation_seeded", "reputation_updated"}
                    and transaction.payload.get("wallet") == wallet
                ):
                    history.append(
                        {
                            "type": transaction.type,
                            "tx_hash": transaction.tx_hash,
                            "block_number": block.number,
                            "timestamp": transaction.timestamp,
                            **transaction.payload,
                        }
                    )
        return history

    def export_blocks(self, limit: int = 100) -> list[dict[str, Any]]:
        self._require_connected()
        newest_first = list(reversed(self._blocks))
        return [block.model_dump(mode="json") for block in newest_first[:limit]]

    def verify(self) -> dict[str, Any]:
        self._require_connected()
        try:
            self._verify_blocks(self._blocks)
            valid, error = True, None
        except RuntimeError as exc:
            valid, error = False, str(exc)
        return {
            "valid": valid,
            "error": error,
            "network": NETWORK_NAME,
            "chain_id": self.chain_id,
            "height": self.height,
            "blocks": len(self._blocks),
            "transactions": sum(len(block.transactions) for block in self._blocks),
            "authority": self.signer_address,
            "verified_at": _utcnow_iso(),
        }

    def _authority_key(self) -> str:
        if self.settings.signer_private_key:
            return _as_0x_hex(self.settings.signer_private_key)
        derived = hashlib.sha256(
            f"{self.settings.secret_key}:medchain-consortium-authority".encode()
        ).hexdigest()
        return f"0x{derived}"

    def _make_transaction(self, tx_type: TransactionType, payload: dict[str, Any]) -> ChainTransaction:
        transaction = ChainTransaction(
            tx_hash="",
            type=tx_type,
            payload=payload,
            timestamp=_utcnow_iso(),
            signer=self.signer_address or "",
            signature="",
        )
        transaction.tx_hash = transaction.content_hash()
        transaction.signature = self._sign(transaction.tx_hash)
        return transaction

    async def _append_block(self, transactions: list[ChainTransaction]) -> Block:
        previous_hash = self._blocks[-1].hash if self._blocks else GENESIS_PREVIOUS_HASH
        block = Block(
            id="",
            chain_id=self.chain_id,
            number=self._blocks[-1].number + 1 if self._blocks else 0,
            timestamp=_utcnow_iso(),
            previous_hash=previous_hash,
            merkle_root=_merkle_root([transaction.tx_hash for transaction in transactions]),
            transactions=transactions,
            hash="",
            signer=self.signer_address or "",
            signature="",
        )
        block.id = f"blk_{block.number:012d}"
        block.hash = block.header_hash()
        block.signature = self._sign(block.hash)
        await self.repo.put(CHAIN_COLLECTION, block)
        self._blocks.append(block)
        for transaction in transactions:
            self._apply_transaction(transaction)
        return block

    def _replay_state(self) -> None:
        self._nodes = {}
        self._reputation = {}
        self._contributions = set()
        for block in self._blocks:
            for transaction in block.transactions:
                self._apply_transaction(transaction)

    def _apply_transaction(self, transaction: ChainTransaction) -> None:
        payload = transaction.payload
        if transaction.type == "node_registered":
            self._nodes[payload["wallet"]] = NodeRecord(
                org_id=payload["org_id"],
                role=payload["role"],
                active=True,
                registered_at=transaction.timestamp,
            )
        elif transaction.type == "node_activated":
            node = self._nodes.get(payload["wallet"])
            if node is not None:
                node.active = bool(payload["active"])
        elif transaction.type == "reputation_seeded":
            self._reputation[payload["wallet"]] = int(payload["score"])
        elif transaction.type == "reputation_updated":
            self._reputation[payload["wallet"]] = int(payload["score"])
        elif transaction.type == "contribution_recorded":
            self._contributions.add((payload["round_hash"], payload["contributor"]))

    def _verify_blocks(self, blocks: list[Block]) -> None:
        previous_hash = GENESIS_PREVIOUS_HASH
        authority = blocks[0].signer if blocks else None
        for expected_number, block in enumerate(blocks):
            label = f"block {block.number}"
            if block.number != expected_number:
                raise RuntimeError(f"Chain is missing a block before {label}")
            if block.chain_id != self.chain_id:
                raise RuntimeError(f"{label} belongs to chain {block.chain_id}, expected {self.chain_id}")
            if block.previous_hash != previous_hash:
                raise RuntimeError(f"{label} does not link to the previous block hash")
            if block.merkle_root != _merkle_root([tx.tx_hash for tx in block.transactions]):
                raise RuntimeError(f"{label} merkle root does not match its transactions")
            if block.hash != block.header_hash():
                raise RuntimeError(f"{label} header hash does not match its contents")
            if block.signer != authority or self._recover(block.hash, block.signature) != block.signer:
                raise RuntimeError(f"{label} was not signed by the consortium authority")
            for transaction in block.transactions:
                if transaction.tx_hash != transaction.content_hash():
                    raise RuntimeError(f"A transaction in {label} was altered after signing")
                if self._recover(transaction.tx_hash, transaction.signature) != transaction.signer:
                    raise RuntimeError(f"A transaction signature in {label} is invalid")
            previous_hash = block.hash

    def _sign(self, hex_hash: str) -> str:
        signed = self._account.sign_message(encode_defunct(hexstr=hex_hash))
        return _as_0x_hex(signed.signature)

    @staticmethod
    def _recover(hex_hash: str, signature: str) -> str:
        try:
            return Account.recover_message(encode_defunct(hexstr=hex_hash), signature=signature)
        except Exception:  # noqa: BLE001 - any malformed signature means tampering
            return ""

    @staticmethod
    def _normalize_wallet(wallet_address: str) -> str:
        if not re.fullmatch(r"0x[0-9a-fA-F]{40}", wallet_address or ""):
            raise RuntimeError("Wallet must be a 20-byte 0x-prefixed address")
        return wallet_address.lower()

    def _require_connected(self) -> None:
        if not self.connected:
            raise RuntimeError("Blockchain service is not connected")
