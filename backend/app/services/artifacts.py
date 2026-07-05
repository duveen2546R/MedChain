from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from ..config import Settings


class ArtifactStore:
    """Private Azure Blob Storage for model updates and aggregated models."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._service_client: Any = None
        self._container_client: Any = None
        self._credential: Any = None
        self.connected = False

    async def connect(self) -> None:
        try:
            from azure.identity import DefaultAzureCredential
            from azure.storage.blob import BlobServiceClient
        except ImportError as exc:
            raise RuntimeError(
                "Azure Blob dependencies are missing; install backend/requirements.txt"
            ) from exc

        if self.settings.azure_storage_connection_string:
            self._service_client = BlobServiceClient.from_connection_string(
                self.settings.azure_storage_connection_string
            )
        else:
            self._credential = DefaultAzureCredential()
            self._service_client = BlobServiceClient(
                account_url=self.settings.azure_storage_account_url,
                credential=self._credential,
            )

        self._container_client = self._service_client.get_container_client(
            self.settings.azure_storage_container
        )
        try:
            await asyncio.to_thread(self._container_client.get_container_properties)
        except Exception as exc:
            await self.close()
            raise RuntimeError(
                f"Cannot access Azure Blob container '{self.settings.azure_storage_container}'"
            ) from exc
        self.connected = True

    async def close(self) -> None:
        if self._service_client is not None:
            await asyncio.to_thread(self._service_client.close)
        if self._credential is not None:
            await asyncio.to_thread(self._credential.close)
        self._service_client = None
        self._container_client = None
        self._credential = None
        self.connected = False

    async def put_json(self, namespace: str, payload: dict[str, Any]) -> tuple[str, str]:
        data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return await self.put_bytes(namespace, data)

    async def put_bytes(self, namespace: str, data: bytes) -> tuple[str, str]:
        if not self.connected or self._container_client is None:
            raise RuntimeError("Azure Blob Storage is not connected")

        from azure.core.exceptions import ResourceExistsError
        from azure.storage.blob import ContentSettings

        digest = hashlib.sha256(data).hexdigest()
        blob_name = f"{namespace}/{digest}.json"
        blob_client = self._container_client.get_blob_client(blob_name)
        try:
            await asyncio.to_thread(
                blob_client.upload_blob,
                data,
                overwrite=False,
                metadata={"sha256": digest},
                content_settings=ContentSettings(content_type="application/json"),
            )
        except ResourceExistsError:
            # Content-addressed names make an existing blob the same artifact.
            pass
        return blob_client.url, f"0x{digest}"
