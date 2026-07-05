from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@dataclass(frozen=True)
class Settings:
    app_name: str = "MedChain AI Backend"
    api_prefix: str = ""
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    secret_key: str = ""
    access_token_minutes: int = 120
    mongodb_uri: str | None = None
    mongodb_name: str = "medchain"
    azure_storage_connection_string: str | None = None
    azure_storage_account_url: str | None = None
    azure_storage_container: str | None = None
    evm_rpc_url: str | None = None
    evm_chain_id: int | None = None
    evm_signer_private_key: str | None = None
    consortium_registry_address: str | None = None
    reputation_registry_address: str | None = None
    training_ledger_address: str | None = None
    evm_receipt_timeout_seconds: int = 120
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    bootstrap_admin_name: str = "Platform Administrator"

    def validate(
        self,
        require_mongodb: bool = True,
        require_azure_storage: bool = True,
        require_blockchain: bool = True,
    ) -> None:
        if len(self.secret_key) < 32:
            raise RuntimeError("MEDCHAIN_SECRET_KEY must contain at least 32 characters")
        if require_mongodb and not self.mongodb_uri:
            raise RuntimeError("MEDCHAIN_MONGODB_URI is required")
        if require_azure_storage:
            if not self.azure_storage_container:
                raise RuntimeError("AZURE_STORAGE_CONTAINER is required")
            if not self.azure_storage_connection_string and not self.azure_storage_account_url:
                raise RuntimeError(
                    "AZURE_STORAGE_CONNECTION_STRING or AZURE_STORAGE_ACCOUNT_URL is required"
                )
        if require_blockchain:
            blockchain_values = {
                "MEDCHAIN_EVM_RPC_URL": self.evm_rpc_url,
                "MEDCHAIN_EVM_CHAIN_ID": self.evm_chain_id,
                "MEDCHAIN_EVM_SIGNER_PRIVATE_KEY": self.evm_signer_private_key,
                "MEDCHAIN_CONSORTIUM_REGISTRY_ADDRESS": self.consortium_registry_address,
                "MEDCHAIN_REPUTATION_REGISTRY_ADDRESS": self.reputation_registry_address,
                "MEDCHAIN_TRAINING_LEDGER_ADDRESS": self.training_ledger_address,
            }
            missing = [name for name, value in blockchain_values.items() if value in {None, ""}]
            if missing:
                raise RuntimeError(f"Missing blockchain configuration: {', '.join(missing)}")
            if not re.fullmatch(r"(?:0x)?[0-9a-fA-F]{64}", self.evm_signer_private_key or ""):
                raise RuntimeError("MEDCHAIN_EVM_SIGNER_PRIVATE_KEY must be a 32-byte hex private key")
            for name, address in (
                ("MEDCHAIN_CONSORTIUM_REGISTRY_ADDRESS", self.consortium_registry_address),
                ("MEDCHAIN_REPUTATION_REGISTRY_ADDRESS", self.reputation_registry_address),
                ("MEDCHAIN_TRAINING_LEDGER_ADDRESS", self.training_ledger_address),
            ):
                if not re.fullmatch(r"0x[0-9a-fA-F]{40}", address or ""):
                    raise RuntimeError(f"{name} must be an EVM contract address")
        if bool(self.bootstrap_admin_email) != bool(self.bootstrap_admin_password):
            raise RuntimeError(
                "MEDCHAIN_BOOTSTRAP_ADMIN_EMAIL and MEDCHAIN_BOOTSTRAP_ADMIN_PASSWORD must be set together"
            )
        if self.bootstrap_admin_password and len(self.bootstrap_admin_password) < 12:
            raise RuntimeError("MEDCHAIN_BOOTSTRAP_ADMIN_PASSWORD must contain at least 12 characters")

    @classmethod
    def from_env(cls) -> "Settings":
        cors = os.getenv("MEDCHAIN_CORS_ORIGINS")
        return cls(
            cors_origins=(
                tuple(item.strip() for item in cors.split(",") if item.strip())
                if cors
                else cls.cors_origins
            ),
            secret_key=os.getenv("MEDCHAIN_SECRET_KEY", ""),
            access_token_minutes=int(os.getenv("MEDCHAIN_ACCESS_TOKEN_MINUTES", "120")),
            mongodb_uri=os.getenv("MEDCHAIN_MONGODB_URI"),
            mongodb_name=os.getenv("MEDCHAIN_MONGODB_NAME", cls.mongodb_name),
            azure_storage_connection_string=os.getenv("AZURE_STORAGE_CONNECTION_STRING"),
            azure_storage_account_url=os.getenv("AZURE_STORAGE_ACCOUNT_URL"),
            azure_storage_container=os.getenv("AZURE_STORAGE_CONTAINER"),
            evm_rpc_url=os.getenv("MEDCHAIN_EVM_RPC_URL"),
            evm_chain_id=(
                int(os.environ["MEDCHAIN_EVM_CHAIN_ID"])
                if os.getenv("MEDCHAIN_EVM_CHAIN_ID")
                else None
            ),
            evm_signer_private_key=os.getenv("MEDCHAIN_EVM_SIGNER_PRIVATE_KEY"),
            consortium_registry_address=os.getenv("MEDCHAIN_CONSORTIUM_REGISTRY_ADDRESS"),
            reputation_registry_address=os.getenv("MEDCHAIN_REPUTATION_REGISTRY_ADDRESS"),
            training_ledger_address=os.getenv("MEDCHAIN_TRAINING_LEDGER_ADDRESS"),
            evm_receipt_timeout_seconds=int(os.getenv("MEDCHAIN_EVM_RECEIPT_TIMEOUT_SECONDS", "120")),
            bootstrap_admin_email=os.getenv("MEDCHAIN_BOOTSTRAP_ADMIN_EMAIL"),
            bootstrap_admin_password=os.getenv("MEDCHAIN_BOOTSTRAP_ADMIN_PASSWORD"),
            bootstrap_admin_name=os.getenv("MEDCHAIN_BOOTSTRAP_ADMIN_NAME", cls.bootstrap_admin_name),
        )


settings = Settings.from_env()
