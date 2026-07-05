from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class MemoryBlockchainService:
    """Test-only blockchain recorder; production signs real EVM transactions."""

    def __init__(self) -> None:
        self.connected = False
        self.chain_id = 31337
        self.signer_address = "0x00000000000000000000000000000000000000aa"
        self.contributions: list[dict[str, Any]] = []

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.connected = False

    async def register_hospital(
        self,
        wallet_address: str,
        org_id: str,
        reputation: int,
    ) -> SimpleNamespace:
        digest = hashlib.sha256(f"{wallet_address}:{org_id}:{reputation}".encode()).hexdigest()
        return SimpleNamespace(
            registry_tx_hash=f"0x{digest}",
            reputation_tx_hash=f"0x{digest[::-1]}",
        )

    async def record_contribution(self, **payload: Any) -> SimpleNamespace:
        self.contributions.append(payload)
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return SimpleNamespace(tx_hash=f"0x{digest}", block_number=len(self.contributions))


class MemoryArtifactStore:
    """Test-only artifact store; production always uses Azure Blob Storage."""

    def __init__(self) -> None:
        self.connected = False
        self.objects: dict[str, bytes] = {}

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.connected = False

    async def put_json(self, namespace: str, payload: dict[str, Any]) -> tuple[str, str]:
        data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(data).hexdigest()
        object_name = f"{namespace}/{digest}.json"
        self.objects[object_name] = data
        return f"memory://{object_name}", f"0x{digest}"


class MemoryRepository:
    """Test-only repository; production always uses MongoDB."""

    def __init__(self) -> None:
        self._collections: dict[str, dict[str, BaseModel]] = {}

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def mongo_enabled(self) -> bool:
        return True

    async def put(self, collection: str, item: T) -> T:
        self._collections.setdefault(collection, {})[getattr(item, "id")] = item
        return item

    async def get(self, collection: str, item_id: str, model_type: type[T]) -> T | None:
        _ = model_type
        return self._collections.get(collection, {}).get(item_id)  # type: ignore[return-value]

    async def find_one(self, collection: str, model_type: type[T], **filters: Any) -> T | None:
        _ = model_type
        for item in self._collections.get(collection, {}).values():
            if all(getattr(item, key) == value for key, value in filters.items()):
                return item  # type: ignore[return-value]
        return None

    async def list(self, collection: str, model_type: type[T], **filters: Any) -> list[T]:
        _ = model_type
        values = list(self._collections.get(collection, {}).values())
        if filters:
            values = [
                item
                for item in values
                if all(getattr(item, key) == value for key, value in filters.items())
            ]
        return values  # type: ignore[return-value]

    async def delete_all(self, collection: str) -> None:
        self._collections[collection] = {}

    async def count(self, collection: str) -> int:
        return len(self._collections.get(collection, {}))
