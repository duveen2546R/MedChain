from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..models import (
    AccessRequest,
    Invitation,
    Organization,
    PasswordResetToken,
    Role,
    User,
    utcnow,
)
from ..security import create_token_pair, hash_password, verify_password
from ..store import Repository
from .dependencies import get_current_user, get_repo, require_roles

auth_router = APIRouter()

# Access-request approval maps an org type to the role its first user receives.
# Clinics are not in the public request flow (a platform_admin invites clinic_users directly).
ORG_ADMIN_ROLE: dict[str, str] = {
    "hospital": "hospital_admin",
    "research": "research_partner",
}
# Tier default when an organization is created (approval or an inline new_org invitation).
ORG_TIER: dict[str, str] = {
    "hospital": "consortium_node",
    "clinic": "clinic",
    "research": "partner",
}
HOSPITAL_ADMIN_INVITABLE: set[str] = {"hospital_node", "clinic_user"}


# --------------------------------------------------------------------------- schemas


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str
    user_id: str
    name: str | None = None
    email: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class AccessRequestCreate(BaseModel):
    organization_name: str = Field(min_length=1)
    organization_type: Literal["hospital", "research"]
    contact_name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    message: str = ""


class AccessRequestReject(BaseModel):
    reason: str = ""


class NewOrg(BaseModel):
    name: str = Field(min_length=1)
    type: Literal["hospital", "clinic", "research"]
    tier: str | None = None


class InvitationCreate(BaseModel):
    email: str = Field(min_length=3)
    role: Role
    org_id: str | None = None
    new_org: NewOrg | None = None


class RegisterRequest(BaseModel):
    token: str
    name: str = Field(min_length=1)
    password: str = Field(min_length=8)


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8)


# --------------------------------------------------------------------------- helpers


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _valid_email(email: str) -> bool:
    return "@" in email and "." in email.split("@")[-1]


def _token_response(user: User, settings: Any) -> TokenResponse:
    access, refresh = create_token_pair(
        {"sub": user.id, "role": user.role, "org_id": user.org_id},
        settings,
    )
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        role=user.role,
        user_id=user.id,
        name=user.name,
        email=user.email,
    )


def _invitation_status(invitation: Invitation, now: datetime) -> str:
    if invitation.accepted_at is not None:
        return "accepted"
    if invitation.revoked_at is not None:
        return "revoked"
    if invitation.expires_at < now:
        return "expired"
    return "pending"


async def _has_live_invitation(repo: Repository, email: str, now: datetime) -> bool:
    for invitation in await repo.list("invitations", Invitation, email=email):
        if _invitation_status(invitation, now) == "pending":
            return True
    return False


# --------------------------------------------------------------------------- session


@auth_router.post("/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, repo: Repository = Depends(get_repo)) -> TokenResponse:
    settings = request.app.state.settings
    email = _normalize_email(body.email)
    user = await repo.find_one("users", User, email=email)
    if not user or not verify_password(body.password, user.password_hash, settings):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.active:
        raise HTTPException(status_code=401, detail="Account is inactive")
    return _token_response(user, settings)


@auth_router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, request: Request, repo: Repository = Depends(get_repo)) -> TokenResponse:
    from ..security import decode_token

    settings = request.app.state.settings
    claims = decode_token(body.refresh_token, settings, expected_type="refresh")
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    user = await repo.get("users", claims["sub"], User)
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="Inactive user")
    return _token_response(user, settings)


@auth_router.post("/auth/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, request: Request, repo: Repository = Depends(get_repo)) -> TokenResponse:
    settings = request.app.state.settings
    runtime = request.app.state.runtime
    now = utcnow()
    invitation = await repo.find_one("invitations", Invitation, token=body.token)
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    status = _invitation_status(invitation, now)
    if status != "pending":
        raise HTTPException(status_code=410, detail=f"Invitation is {status}")
    if await repo.find_one("users", User, email=invitation.email):
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = await repo.put(
        "users",
        User(
            email=invitation.email,
            name=body.name.strip(),
            role=invitation.role,
            org_id=invitation.org_id,
            password_hash=hash_password(body.password, settings),
        ),
    )
    invitation.accepted_at = now
    await repo.put("invitations", invitation)
    await runtime.audit.record("auth.registered", "user", user.id, user)
    await runtime.audit.record("invitation.accepted", "invitation", invitation.id, user)
    return _token_response(user, settings)


# --------------------------------------------------------------------------- access requests


@auth_router.post("/auth/access-requests", status_code=201)
async def submit_access_request(
    body: AccessRequestCreate,
    request: Request,
    repo: Repository = Depends(get_repo),
) -> dict[str, Any]:
    runtime = request.app.state.runtime
    email = _normalize_email(body.email)
    if not _valid_email(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    if await repo.find_one("users", User, email=email):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    pending = [
        req
        for req in await repo.list("access_requests", AccessRequest, email=email)
        if req.status == "pending"
    ]
    if pending:
        raise HTTPException(status_code=409, detail="A request for this email is already pending review")

    access_request = await repo.put(
        "access_requests",
        AccessRequest(
            organization_name=body.organization_name.strip(),
            organization_type=body.organization_type,
            contact_name=body.contact_name.strip(),
            email=email,
            message=body.message.strip(),
        ),
    )
    await runtime.audit.record(
        "access_request.submitted",
        "access_request",
        access_request.id,
        None,
        {"email": email, "organization_type": body.organization_type},
    )
    return {"ok": True, "request_id": access_request.id}


@auth_router.get("/auth/access-requests")
async def list_access_requests(
    status: str | None = None,
    repo: Repository = Depends(get_repo),
    user: User = Depends(require_roles("platform_admin")),
) -> list[dict[str, Any]]:
    _ = user
    filters = {"status": status} if status else {}
    requests = await repo.list("access_requests", AccessRequest, **filters)
    requests.sort(key=lambda req: req.created_at, reverse=True)
    return [req.model_dump(mode="json") for req in requests]


@auth_router.post("/auth/access-requests/{request_id}/approve")
async def approve_access_request(
    request_id: str,
    request: Request,
    repo: Repository = Depends(get_repo),
    user: User = Depends(require_roles("platform_admin")),
) -> dict[str, Any]:
    settings = request.app.state.settings
    runtime = request.app.state.runtime
    now = utcnow()
    access_request = await repo.get("access_requests", request_id, AccessRequest)
    if access_request is None:
        raise HTTPException(status_code=404, detail="Access request not found")
    if access_request.status != "pending":
        raise HTTPException(status_code=409, detail=f"Access request is already {access_request.status}")

    org_type = access_request.organization_type
    org = await repo.put(
        "organizations",
        Organization(
            name=access_request.organization_name,
            type=org_type,
            tier=ORG_TIER[org_type],
        ),
    )
    invitation = await repo.put(
        "invitations",
        Invitation(
            email=access_request.email,
            role=ORG_ADMIN_ROLE[org_type],
            org_id=org.id,
            invited_by=user.id,
            expires_at=now + timedelta(days=settings.invitation_expires_days),
        ),
    )
    access_request.status = "approved"
    access_request.reviewed_by = user.id
    access_request.reviewed_at = now
    access_request.org_id = org.id
    access_request.invitation_id = invitation.id
    await repo.put("access_requests", access_request)

    email_sent = await runtime.notifications.send_invitation(invitation, org.name)
    await runtime.audit.record("access_request.approved", "access_request", access_request.id, user)
    await runtime.audit.record("invitation.created", "invitation", invitation.id, user)
    return {
        "request": access_request.model_dump(mode="json"),
        "invitation": invitation.model_dump(mode="json"),
        "invite_url": runtime.notifications.invite_url(invitation.token),
        "email_sent": email_sent,
    }


@auth_router.post("/auth/access-requests/{request_id}/reject")
async def reject_access_request(
    request_id: str,
    body: AccessRequestReject,
    request: Request,
    repo: Repository = Depends(get_repo),
    user: User = Depends(require_roles("platform_admin")),
) -> dict[str, Any]:
    runtime = request.app.state.runtime
    now = utcnow()
    access_request = await repo.get("access_requests", request_id, AccessRequest)
    if access_request is None:
        raise HTTPException(status_code=404, detail="Access request not found")
    if access_request.status != "pending":
        raise HTTPException(status_code=409, detail=f"Access request is already {access_request.status}")

    access_request.status = "rejected"
    access_request.reviewed_by = user.id
    access_request.reviewed_at = now
    access_request.rejection_reason = body.reason.strip() or None
    await repo.put("access_requests", access_request)
    await runtime.notifications.send_access_request_rejected(access_request)
    await runtime.audit.record("access_request.rejected", "access_request", access_request.id, user)
    return {"request": access_request.model_dump(mode="json")}


# --------------------------------------------------------------------------- invitations


@auth_router.post("/auth/invitations", status_code=201)
async def create_invitation(
    body: InvitationCreate,
    request: Request,
    repo: Repository = Depends(get_repo),
    user: User = Depends(require_roles("platform_admin", "hospital_admin")),
) -> dict[str, Any]:
    settings = request.app.state.settings
    runtime = request.app.state.runtime
    now = utcnow()
    email = _normalize_email(body.email)
    if not _valid_email(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address")

    if user.role == "hospital_admin":
        if body.role not in HOSPITAL_ADMIN_INVITABLE:
            raise HTTPException(status_code=403, detail="You may only invite hospital nodes or clinic users")
        if body.new_org is not None:
            raise HTTPException(status_code=403, detail="You cannot create organizations")
        if body.org_id is not None and body.org_id != user.org_id:
            raise HTTPException(status_code=403, detail="You may only invite into your own organization")
        org = await repo.get("organizations", user.org_id, Organization)
        if org is None:
            raise HTTPException(status_code=400, detail="Your organization no longer exists")
    else:  # platform_admin — any role, any org
        if body.org_id is not None and body.new_org is not None:
            raise HTTPException(status_code=400, detail="Provide either org_id or new_org, not both")
        if body.new_org is not None:
            org = await repo.put(
                "organizations",
                Organization(
                    name=body.new_org.name.strip(),
                    type=body.new_org.type,
                    tier=body.new_org.tier or ORG_TIER[body.new_org.type],
                ),
            )
        elif body.org_id is not None:
            org = await repo.get("organizations", body.org_id, Organization)
            if org is None:
                raise HTTPException(status_code=404, detail="Organization not found")
        else:
            org = await repo.find_one("organizations", Organization, type="platform")
            if org is None:
                raise HTTPException(status_code=400, detail="org_id or new_org is required")

    if await repo.find_one("users", User, email=email):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    if await _has_live_invitation(repo, email, now):
        raise HTTPException(status_code=409, detail="A pending invitation for this email already exists")

    invitation = await repo.put(
        "invitations",
        Invitation(
            email=email,
            role=body.role,
            org_id=org.id,
            invited_by=user.id,
            expires_at=now + timedelta(days=settings.invitation_expires_days),
        ),
    )
    email_sent = await runtime.notifications.send_invitation(invitation, org.name)
    await runtime.audit.record("invitation.created", "invitation", invitation.id, user)
    return {
        "invitation": invitation.model_dump(mode="json"),
        "invite_url": runtime.notifications.invite_url(invitation.token),
        "email_sent": email_sent,
    }


@auth_router.get("/auth/invitations")
async def list_invitations(
    repo: Repository = Depends(get_repo),
    user: User = Depends(require_roles("platform_admin", "hospital_admin")),
) -> list[dict[str, Any]]:
    now = utcnow()
    filters = {} if user.role == "platform_admin" else {"org_id": user.org_id}
    invitations = await repo.list("invitations", Invitation, **filters)
    invitations.sort(key=lambda inv: inv.created_at, reverse=True)
    orgs = {org.id: org.name for org in await repo.list("organizations", Organization)}
    return [
        {
            **invitation.model_dump(mode="json"),
            "status": _invitation_status(invitation, now),
            "org_name": orgs.get(invitation.org_id),
        }
        for invitation in invitations
    ]


@auth_router.post("/auth/invitations/{invitation_id}/revoke")
async def revoke_invitation(
    invitation_id: str,
    request: Request,
    repo: Repository = Depends(get_repo),
    user: User = Depends(require_roles("platform_admin", "hospital_admin")),
) -> dict[str, Any]:
    runtime = request.app.state.runtime
    invitation = await repo.get("invitations", invitation_id, Invitation)
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if user.role == "hospital_admin" and invitation.org_id != user.org_id:
        raise HTTPException(status_code=403, detail="You may only revoke invitations in your organization")
    if invitation.accepted_at is not None:
        raise HTTPException(status_code=409, detail="Invitation has already been accepted")

    invitation.revoked_at = utcnow()
    await repo.put("invitations", invitation)
    await runtime.audit.record("invitation.revoked", "invitation", invitation.id, user)
    return {"invitation": invitation.model_dump(mode="json")}


@auth_router.get("/auth/invitations/token/{token}")
async def preview_invitation(token: str, repo: Repository = Depends(get_repo)) -> dict[str, Any]:
    now = utcnow()
    invitation = await repo.find_one("invitations", Invitation, token=token)
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    status = _invitation_status(invitation, now)
    if status != "pending":
        raise HTTPException(status_code=410, detail=f"Invitation is {status}")
    org = await repo.get("organizations", invitation.org_id, Organization)
    return {
        "org_name": org.name if org else None,
        "role": invitation.role,
        "email": invitation.email,
        "expires_at": invitation.expires_at.isoformat(),
        "valid": True,
    }


# --------------------------------------------------------------------------- password reset


@auth_router.post("/auth/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    repo: Repository = Depends(get_repo),
) -> dict[str, Any]:
    settings = request.app.state.settings
    runtime = request.app.state.runtime
    now = utcnow()
    email = _normalize_email(body.email)
    user = await repo.find_one("users", User, email=email)
    if user is not None:
        # Invalidate any prior unused reset tokens for this user.
        for token in await repo.list("password_reset_tokens", PasswordResetToken, user_id=user.id, used_at=None):
            token.used_at = now
            await repo.put("password_reset_tokens", token)
        reset = await repo.put(
            "password_reset_tokens",
            PasswordResetToken(
                user_id=user.id,
                expires_at=now + timedelta(minutes=settings.reset_token_minutes),
            ),
        )
        await runtime.notifications.send_password_reset(user, reset.token)
        await runtime.audit.record("auth.password_reset_requested", "user", user.id, user)
    # Anti-enumeration: identical response whether or not the account exists.
    return {"ok": True}


@auth_router.post("/auth/reset-password")
async def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    repo: Repository = Depends(get_repo),
) -> dict[str, Any]:
    settings = request.app.state.settings
    runtime = request.app.state.runtime
    now = utcnow()
    reset = await repo.find_one("password_reset_tokens", PasswordResetToken, token=body.token)
    if reset is None or reset.used_at is not None or reset.expires_at < now:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    user = await repo.get("users", reset.user_id, User)
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user.password_hash = hash_password(body.password, settings)
    await repo.put("users", user)
    reset.used_at = now
    await repo.put("password_reset_tokens", reset)
    await runtime.audit.record("auth.password_reset_completed", "user", user.id, user)
    return {"ok": True}
