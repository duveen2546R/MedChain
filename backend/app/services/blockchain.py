from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from ..config import Settings


REGISTRY_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "node", "type": "address"},
            {"internalType": "string", "name": "orgId", "type": "string"},
            {"internalType": "bytes32", "name": "role", "type": "bytes32"},
        ],
        "name": "registerNode",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "node", "type": "address"},
            {"internalType": "bool", "name": "active", "type": "bool"},
        ],
        "name": "setNodeActive",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "node", "type": "address"}],
        "name": "getNode",
        "outputs": [
            {"internalType": "string", "name": "orgId", "type": "string"},
            {"internalType": "bytes32", "name": "role", "type": "bytes32"},
            {"internalType": "bool", "name": "active", "type": "bool"},
            {"internalType": "uint256", "name": "registeredAt", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "owner",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]

REPUTATION_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "node", "type": "address"},
            {"internalType": "uint256", "name": "score", "type": "uint256"},
        ],
        "name": "seedReputation",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "", "type": "address"}],
        "name": "reputation",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "owner",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]

LEDGER_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "roundId", "type": "bytes32"},
            {"internalType": "string", "name": "modelVersion", "type": "string"},
            {"internalType": "address", "name": "contributor", "type": "address"},
            {"internalType": "bytes32", "name": "updateHash", "type": "bytes32"},
            {"internalType": "string", "name": "artifactCid", "type": "string"},
            {"internalType": "bool", "name": "validated", "type": "bool"},
        ],
        "name": "recordContribution",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "", "type": "bytes32"},
            {"internalType": "address", "name": "", "type": "address"},
        ],
        "name": "submittedByRound",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "owner",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "registry",
        "outputs": [{"internalType": "contract IConsortiumRegistry", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "reputation",
        "outputs": [{"internalType": "contract IReputationRegistry", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]


@dataclass(frozen=True)
class TransactionReceipt:
    tx_hash: str
    block_number: int


@dataclass(frozen=True)
class RegistrationReceipt:
    registry_tx_hash: str | None
    reputation_tx_hash: str | None


class BlockchainService:
    """Signs and confirms real transactions against the MedChain contracts."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.connected = False
        self.chain_id: int | None = None
        self.signer_address: str | None = None
        self._web3: Any = None
        self._account: Any = None
        self._registry: Any = None
        self._reputation: Any = None
        self._ledger: Any = None
        self._transaction_lock = asyncio.Lock()

    async def connect(self) -> None:
        await asyncio.to_thread(self._connect)

    def _connect(self) -> None:
        from web3 import Web3

        self._web3 = Web3(Web3.HTTPProvider(self.settings.evm_rpc_url, request_kwargs={"timeout": 15}))
        if not self._web3.is_connected():
            raise RuntimeError("Cannot connect to MEDCHAIN_EVM_RPC_URL")

        self.chain_id = self._web3.eth.chain_id
        if self.chain_id != self.settings.evm_chain_id:
            raise RuntimeError(
                f"EVM chain id mismatch: expected {self.settings.evm_chain_id}, received {self.chain_id}"
            )

        self._account = self._web3.eth.account.from_key(self.settings.evm_signer_private_key)
        self.signer_address = self._account.address
        self._registry = self._contract(self.settings.consortium_registry_address, REGISTRY_ABI)
        self._reputation = self._contract(self.settings.reputation_registry_address, REPUTATION_ABI)
        self._ledger = self._contract(self.settings.training_ledger_address, LEDGER_ABI)

        for name, contract in (
            ("ConsortiumRegistry", self._registry),
            ("ReputationRegistry", self._reputation),
            ("TrainingLedger", self._ledger),
        ):
            owner = self._web3.to_checksum_address(contract.functions.owner().call())
            if owner != self.signer_address:
                raise RuntimeError(f"Configured signer is not the owner of {name}")

        ledger_registry = self._web3.to_checksum_address(self._ledger.functions.registry().call())
        ledger_reputation = self._web3.to_checksum_address(self._ledger.functions.reputation().call())
        if ledger_registry != self._registry.address or ledger_reputation != self._reputation.address:
            raise RuntimeError("TrainingLedger is connected to different registry contracts")
        self.connected = True

    def _contract(self, address: str | None, abi: list[dict[str, Any]]) -> Any:
        checksum = self._web3.to_checksum_address(address)
        if not self._web3.eth.get_code(checksum):
            raise RuntimeError(f"No contract code exists at {checksum}")
        return self._web3.eth.contract(address=checksum, abi=abi)

    async def close(self) -> None:
        if self._web3 is not None and hasattr(self._web3.provider, "disconnect"):
            await asyncio.to_thread(self._web3.provider.disconnect)
        self.connected = False

    async def register_hospital(
        self,
        wallet_address: str,
        org_id: str,
        reputation: int,
    ) -> RegistrationReceipt:
        async with self._transaction_lock:
            return await asyncio.to_thread(
                self._register_hospital,
                wallet_address,
                org_id,
                reputation,
            )

    def _register_hospital(
        self,
        wallet_address: str,
        org_id: str,
        reputation: int,
    ) -> RegistrationReceipt:
        self._require_connected()
        wallet = self._web3.to_checksum_address(wallet_address)
        existing_org, _, active, registered_at = self._registry.functions.getNode(wallet).call()
        registry_tx_hash: str | None = None
        reputation_tx_hash: str | None = None

        if registered_at:
            if existing_org != org_id:
                raise RuntimeError("Wallet is already registered to a different organization")
            if not active:
                registry_tx_hash = self._send(
                    self._registry.functions.setNodeActive(wallet, True)
                ).tx_hash
        else:
            role = self._web3.keccak(text="hospital_node")
            registry_tx_hash = self._send(
                self._registry.functions.registerNode(wallet, org_id, role)
            ).tx_hash

        if self._reputation.functions.reputation(wallet).call() == 0:
            reputation_tx_hash = self._send(
                self._reputation.functions.seedReputation(wallet, reputation)
            ).tx_hash
        return RegistrationReceipt(registry_tx_hash, reputation_tx_hash)

    async def record_contribution(
        self,
        round_id: str,
        model_version: str,
        contributor: str,
        update_hash: str,
        artifact_uri: str,
        validated: bool,
    ) -> TransactionReceipt:
        async with self._transaction_lock:
            return await asyncio.to_thread(
                self._record_contribution,
                round_id,
                model_version,
                contributor,
                update_hash,
                artifact_uri,
                validated,
            )

    def _record_contribution(
        self,
        round_id: str,
        model_version: str,
        contributor: str,
        update_hash: str,
        artifact_uri: str,
        validated: bool,
    ) -> TransactionReceipt:
        self._require_connected()
        round_hash = self._web3.keccak(text=round_id)
        contributor_address = self._web3.to_checksum_address(contributor)
        update_hash_bytes = bytes.fromhex(update_hash.removeprefix("0x"))
        if len(update_hash_bytes) != 32:
            raise RuntimeError("Model update hash must contain 32 bytes")
        if self._ledger.functions.submittedByRound(round_hash, contributor_address).call():
            raise RuntimeError("Contribution is already recorded on-chain")

        return self._send(
            self._ledger.functions.recordContribution(
                round_hash,
                model_version,
                contributor_address,
                update_hash_bytes,
                artifact_uri,
                validated,
            )
        )

    def _send(self, contract_function: Any) -> TransactionReceipt:
        nonce = self._web3.eth.get_transaction_count(self.signer_address, "pending")
        gas = contract_function.estimate_gas({"from": self.signer_address})
        transaction = contract_function.build_transaction(
            {
                "from": self.signer_address,
                "chainId": self.chain_id,
                "nonce": nonce,
                "gas": max(21_000, int(gas * 1.2)),
                "gasPrice": self._web3.eth.gas_price,
            }
        )
        signed = self._account.sign_transaction(transaction)
        tx_hash = self._web3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self._web3.eth.wait_for_transaction_receipt(
            tx_hash,
            timeout=self.settings.evm_receipt_timeout_seconds,
        )
        if receipt.status != 1:
            raise RuntimeError(f"Blockchain transaction reverted: {tx_hash.hex()}")
        return TransactionReceipt(tx_hash.hex(), int(receipt.blockNumber))

    def _require_connected(self) -> None:
        if not self.connected:
            raise RuntimeError("Blockchain service is not connected")
