from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

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
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    bootstrap_admin_name: str = "Platform Administrator"

    def validate(self, require_mongodb: bool = True, require_azure_storage: bool = True) -> None:
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
            bootstrap_admin_email=os.getenv("MEDCHAIN_BOOTSTRAP_ADMIN_EMAIL"),
            bootstrap_admin_password=os.getenv("MEDCHAIN_BOOTSTRAP_ADMIN_PASSWORD"),
            bootstrap_admin_name=os.getenv("MEDCHAIN_BOOTSTRAP_ADMIN_NAME", cls.bootstrap_admin_name),
        )


settings = Settings.from_env()
