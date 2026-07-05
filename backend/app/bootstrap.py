from __future__ import annotations

from .config import Settings
from .models import Organization, User
from .security import hash_password
from .store import Repository


async def bootstrap_admin(repo: Repository, settings: Settings) -> None:
    """Create the explicitly configured first administrator once."""
    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        return

    email = settings.bootstrap_admin_email.strip().lower()
    if await repo.find_one("users", User, email=email):
        return

    organization = await repo.find_one("organizations", Organization, type="platform")
    if organization is None:
        organization = await repo.put(
            "organizations",
            Organization(name="MedChain", type="platform", tier="internal"),
        )

    await repo.put(
        "users",
        User(
            email=email,
            name=settings.bootstrap_admin_name,
            role="platform_admin",
            org_id=organization.id,
            password_hash=hash_password(settings.bootstrap_admin_password, settings),
        ),
    )
