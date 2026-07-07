from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from .config import Settings

T = TypeVar("T", bound=BaseModel)


def dump_model(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


class Repository:
    """MongoDB-backed repository used by the API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: Any = None
        self._db: Any = None

    async def connect(self) -> None:
        if not self.settings.mongodb_uri:
            raise RuntimeError("MEDCHAIN_MONGODB_URI is required")
        from motor.motor_asyncio import AsyncIOMotorClient

        self._client = AsyncIOMotorClient(self.settings.mongodb_uri, serverSelectionTimeoutMS=5000)
        await self._client.admin.command("ping")
        self._db = self._client[self.settings.mongodb_name]
        await self._create_indexes()

    async def close(self) -> None:
        if self._client:
            self._client.close()
        self._client = None
        self._db = None

    def mongo_enabled(self) -> bool:
        return self._db is not None

    async def put(self, collection: str, item: T) -> T:
        db = self._require_db()
        doc = dump_model(item)
        await db[collection].replace_one({"id": doc["id"]}, doc, upsert=True)
        return item

    async def get(self, collection: str, item_id: str, model_type: type[T]) -> T | None:
        doc = await self._require_db()[collection].find_one({"id": item_id}, {"_id": 0})
        return model_type(**doc) if doc else None

    async def find_one(self, collection: str, model_type: type[T], **filters: Any) -> T | None:
        doc = await self._require_db()[collection].find_one(filters, {"_id": 0})
        return model_type(**doc) if doc else None

    async def list(self, collection: str, model_type: type[T], **filters: Any) -> list[T]:
        cursor = self._require_db()[collection].find(filters or {}, {"_id": 0})
        docs = await cursor.to_list(length=None)
        return [model_type(**doc) for doc in docs]

    async def delete_all(self, collection: str) -> None:
        await self._require_db()[collection].delete_many({})

    async def count(self, collection: str) -> int:
        return await self._require_db()[collection].count_documents({})

    def _require_db(self) -> Any:
        if self._db is None:
            raise RuntimeError("MongoDB repository is not connected")
        return self._db

    async def _create_indexes(self) -> None:
        db = self._require_db()
        await db["users"].create_index("email", unique=True)
        await db["submissions"].create_index(
            [("round_id", 1), ("hospital_id", 1)],
            unique=True,
        )
        await db["invitations"].create_index("token", unique=True)
        await db["password_reset_tokens"].create_index("token", unique=True)
