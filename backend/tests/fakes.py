from __future__ import annotations

import hashlib
import json
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


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


class CapturingNotificationService:
    """Test-only notification service; records outgoing email instead of sending."""

    enabled = False

    def __init__(self, frontend_base_url: str = "http://localhost:5173") -> None:
        self.frontend_base_url = frontend_base_url
        self.sent: list[dict[str, Any]] = []

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def invite_url(self, token: str) -> str:
        return f"{self.frontend_base_url}/register?token={token}"

    def reset_url(self, token: str) -> str:
        return f"{self.frontend_base_url}/reset-password?token={token}"

    async def send(self, to_email: str, to_name: str, subject: str, html: str) -> bool:
        self.sent.append({"to": to_email, "subject": subject, "html": html})
        return False

    async def send_invitation(self, invitation: Any, org_name: str) -> bool:
        self.sent.append({"kind": "invitation", "to": invitation.email, "token": invitation.token})
        return False

    async def send_password_reset(self, user: Any, token: str) -> bool:
        self.sent.append({"kind": "password_reset", "to": user.email, "token": token})
        return False

    async def send_access_request_rejected(self, access_request: Any) -> bool:
        self.sent.append({"kind": "access_request_rejected", "to": access_request.email})
        return False


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
