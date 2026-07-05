from __future__ import annotations

from ..models import AuditEvent, User
from ..store import Repository


class AuditService:
    def __init__(self, repo: Repository):
        self.repo = repo

    async def record(
        self,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        actor: User | None = None,
        metadata: dict | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            actor_id=actor.id if actor else None,
            actor_role=actor.role if actor else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata or {},
        )
        return await self.repo.put("audit_events", event)
