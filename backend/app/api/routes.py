from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..models import (
    AuditEvent,
    DashboardSummary,
    Hospital,
    ModelVersion,
    Organization,
    Submission,
    TrainingObjective,
    TrainingRound,
    User,
    new_id,
)
from ..security import create_access_token, hash_password, verify_password
from ..services.runtime import MedChainRuntime
from ..store import Repository
from .dependencies import get_current_user, get_repo, require_roles

router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    organization: str = Field(min_length=1)
    account_type: str = "clinic"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: str
    name: str | None = None
    email: str | None = None


# Public sign-up maps a friendly account type to a role, org type, and tier.
# platform_admin and auditor are intentionally not self-service.
ACCOUNT_TYPES: dict[str, tuple[str, str, str]] = {
    "clinic": ("clinic_user", "clinic", "clinic"),
    "hospital": ("hospital_admin", "hospital", "consortium_node"),
    "research": ("research_partner", "research", "partner"),
}


class HospitalCreate(BaseModel):
    id: str | None = None
    name: str
    region: str
    samples: int = Field(gt=0)
    specialty: str
    reputation: int = Field(default=80, ge=0, le=100)
    org_id: str | None = None
    wallet_address: str = Field(pattern=r"^0x[0-9a-fA-F]{40}$")
    metadata: dict[str, Any] = Field(default_factory=dict)


class HospitalPatch(BaseModel):
    name: str | None = None
    region: str | None = None
    samples: int | None = Field(default=None, gt=0)
    specialty: str | None = None
    reputation: int | None = Field(default=None, ge=0, le=100)
    active: bool | None = None
    wallet_address: str | None = Field(default=None, pattern=r"^0x[0-9a-fA-F]{40}$")
    metadata: dict[str, Any] | None = None


class ObjectiveCreate(BaseModel):
    name: str
    disease_category: str
    specialty: str
    target_metric: str = "accuracy"
    target_value: float = 0.9
    min_participants: int = 3
    routing_metadata: dict[str, Any] = Field(default_factory=dict)


class RoundCreate(BaseModel):
    objective_id: str | None = None


class SubmissionCreate(BaseModel):
    hospital_id: str
    update: dict[str, Any]


def get_runtime(request: Request) -> MedChainRuntime:
    return request.app.state.runtime


def dump(model: Any) -> Any:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    if hasattr(model, "json"):
        return json.loads(model.json())
    return model


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    repo: Repository = request.app.state.repo
    return {
        "ok": True,
        "app": request.app.state.settings.app_name,
        "mongodb_connected": repo.mongo_enabled(),
        "artifact_storage": "azure_blob",
        "azure_blob_connected": request.app.state.runtime.artifacts.connected,
        "blockchain_connected": request.app.state.runtime.blockchain.connected,
        "blockchain_chain_id": request.app.state.runtime.blockchain.chain_id,
        "blockchain_signer": request.app.state.runtime.blockchain.signer_address,
    }


@router.post("/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, repo: Repository = Depends(get_repo)) -> TokenResponse:
    email = body.email.strip().lower()
    user = await repo.find_one("users", User, email=email)
    if not user or not verify_password(body.password, user.password_hash, request.app.state.settings):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(
        {"sub": user.id, "role": user.role, "org_id": user.org_id},
        request.app.state.settings,
    )
    return TokenResponse(access_token=token, role=user.role, user_id=user.id, name=user.name, email=user.email)


@router.post("/auth/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, request: Request, repo: Repository = Depends(get_repo)) -> TokenResponse:
    settings = request.app.state.settings
    email = body.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    if body.account_type not in ACCOUNT_TYPES:
        raise HTTPException(status_code=400, detail="Unknown account type")
    if await repo.find_one("users", User, email=email):
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    role, org_type, tier = ACCOUNT_TYPES[body.account_type]
    org = await repo.put(
        "organizations",
        Organization(name=body.organization.strip(), type=org_type, tier=tier),
    )
    user = await repo.put(
        "users",
        User(
            email=email,
            name=body.name.strip(),
            role=role,
            org_id=org.id,
            password_hash=hash_password(body.password, settings),
        ),
    )
    await request.app.state.runtime.audit.record("auth.registered", "user", user.id, user)
    token = create_access_token(
        {"sub": user.id, "role": user.role, "org_id": user.org_id},
        settings,
    )
    return TokenResponse(access_token=token, role=user.role, user_id=user.id, name=user.name, email=user.email)


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(request: Request, user: User = Depends(get_current_user)) -> TokenResponse:
    token = create_access_token(
        {"sub": user.id, "role": user.role, "org_id": user.org_id},
        request.app.state.settings,
    )
    return TokenResponse(access_token=token, role=user.role, user_id=user.id, name=user.name, email=user.email)


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict[str, Any]:
    payload = dump(user)
    payload.pop("password_hash", None)
    return payload


@router.get("/dashboard/summary", response_model=DashboardSummary)
async def dashboard_summary(
    runtime: MedChainRuntime = Depends(get_runtime),
    user: User = Depends(get_current_user),
) -> DashboardSummary:
    _ = user
    return await runtime.dashboard_summary()


@router.get("/hospitals", response_model=list[Hospital])
async def list_hospitals(
    repo: Repository = Depends(get_repo),
    user: User = Depends(get_current_user),
) -> list[Hospital]:
    _ = user
    return sorted(await repo.list("hospitals", Hospital), key=lambda hospital: hospital.id)


@router.post("/hospitals", response_model=Hospital)
async def create_hospital(
    body: HospitalCreate,
    request: Request,
    repo: Repository = Depends(get_repo),
    user: User = Depends(require_roles("platform_admin")),
) -> Hospital:
    hospital_id = body.id or new_id("hsp")
    if await repo.get("hospitals", hospital_id, Hospital):
        raise HTTPException(status_code=409, detail="Hospital id already exists")

    if body.org_id:
        organization = await repo.get("organizations", body.org_id, Organization)
        if organization is None or organization.type != "hospital":
            raise HTTPException(status_code=400, detail="org_id must identify an existing hospital organization")
    else:
        organization = await repo.put(
            "organizations",
            Organization(name=body.name, type="hospital", tier="consortium_node"),
        )

    hospital = Hospital(
        id=hospital_id,
        org_id=organization.id,
        name=body.name,
        region=body.region,
        samples=body.samples,
        specialty=body.specialty,
        reputation=body.reputation,
        wallet_address=body.wallet_address,
        metadata=body.metadata,
    )
    saved = await repo.put("hospitals", hospital)
    await request.app.state.runtime.audit.record("hospital.created", "hospital", saved.id, user)
    return saved


@router.patch("/hospitals/{hospital_id}", response_model=Hospital)
async def patch_hospital(
    hospital_id: str,
    body: HospitalPatch,
    request: Request,
    repo: Repository = Depends(get_repo),
    user: User = Depends(require_roles("platform_admin", "hospital_admin")),
) -> Hospital:
    hospital = await repo.get("hospitals", hospital_id, Hospital)
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")
    if user.role == "hospital_admin" and user.org_id != hospital.org_id:
        raise HTTPException(status_code=403, detail="Hospital administrators may only edit their own organization")
    patch = body.model_dump(exclude_unset=True)
    if "wallet_address" in patch and patch["wallet_address"] != hospital.wallet_address:
        hospital.blockchain_registered = False
        hospital.registry_tx_hash = None
        hospital.reputation_tx_hash = None
    for key, value in patch.items():
        setattr(hospital, key, value)
    saved = await repo.put("hospitals", hospital)
    await request.app.state.runtime.audit.record("hospital.updated", "hospital", saved.id, user)
    return saved


@router.post("/hospitals/{hospital_id}/blockchain/register", response_model=Hospital)
async def register_hospital_on_chain(
    hospital_id: str,
    runtime: MedChainRuntime = Depends(get_runtime),
    user: User = Depends(require_roles("platform_admin")),
) -> Hospital:
    try:
        return await runtime.register_hospital_on_chain(hospital_id, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/training-objectives", response_model=list[TrainingObjective])
async def list_objectives(
    repo: Repository = Depends(get_repo),
    user: User = Depends(get_current_user),
) -> list[TrainingObjective]:
    _ = user
    return await repo.list("training_objectives", TrainingObjective)


@router.post("/training-objectives", response_model=TrainingObjective)
async def create_objective(
    body: ObjectiveCreate,
    runtime: MedChainRuntime = Depends(get_runtime),
    user: User = Depends(require_roles("platform_admin", "hospital_admin")),
) -> TrainingObjective:
    objective = TrainingObjective(**body.model_dump())
    return await runtime.create_objective(objective, user)


@router.get("/rounds", response_model=list[TrainingRound])
async def list_rounds(
    repo: Repository = Depends(get_repo),
    user: User = Depends(get_current_user),
) -> list[TrainingRound]:
    _ = user
    return sorted(await repo.list("rounds", TrainingRound), key=lambda item: item.round_number)


@router.get("/rounds/{round_id}", response_model=TrainingRound)
async def get_round(
    round_id: str,
    repo: Repository = Depends(get_repo),
    user: User = Depends(get_current_user),
) -> TrainingRound:
    _ = user
    training_round = await repo.get("rounds", round_id, TrainingRound)
    if not training_round:
        raise HTTPException(status_code=404, detail="Round not found")
    return training_round


@router.post("/rounds", response_model=TrainingRound)
async def create_round(
    body: RoundCreate,
    runtime: MedChainRuntime = Depends(get_runtime),
    user: User = Depends(require_roles("platform_admin", "hospital_admin")),
) -> TrainingRound:
    try:
        return await runtime.create_round(body.objective_id, user)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/rounds/{round_id}/blockchain/retry", response_model=TrainingRound)
async def retry_round_blockchain(
    round_id: str,
    runtime: MedChainRuntime = Depends(get_runtime),
    user: User = Depends(require_roles("platform_admin")),
) -> TrainingRound:
    try:
        return await runtime.retry_round_blockchain(round_id, user)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post(
    "/rounds/{round_id}/submissions",
    response_model=Submission,
    response_model_exclude={"weights"},
)
async def submit_update(
    round_id: str,
    body: SubmissionCreate,
    runtime: MedChainRuntime = Depends(get_runtime),
    user: User = Depends(require_roles("hospital_admin", "hospital_node")),
) -> Submission:
    try:
        return await runtime.submit_external_update(round_id, body.hospital_id, body.update, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/model-versions", response_model=list[ModelVersion])
async def list_model_versions(
    repo: Repository = Depends(get_repo),
    user: User = Depends(get_current_user),
) -> list[ModelVersion]:
    _ = user
    return sorted(await repo.list("model_versions", ModelVersion), key=lambda item: item.round)


@router.get("/model-versions/current", response_model=ModelVersion)
async def current_model(
    runtime: MedChainRuntime = Depends(get_runtime),
    user: User = Depends(get_current_user),
) -> ModelVersion:
    _ = user
    try:
        return await runtime.current_model()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/blockchain/contributions")
async def blockchain_contributions(
    repo: Repository = Depends(get_repo),
    user: User = Depends(require_roles("platform_admin", "auditor", "research_partner")),
) -> list[dict[str, Any]]:
    _ = user
    submissions = await repo.list("submissions", Submission)
    results: list[dict[str, Any]] = []
    for submission in submissions:
        if not submission.blockchain_tx_hash:
            continue
        payload = dump(submission)
        payload.pop("weights", None)
        results.append(payload)
    return sorted(results, key=lambda item: item["submitted_at"])


@router.get("/audit/events", response_model=list[AuditEvent])
async def audit_events(
    repo: Repository = Depends(get_repo),
    user: User = Depends(require_roles("platform_admin", "auditor")),
) -> list[AuditEvent]:
    _ = user
    return sorted(await repo.list("audit_events", AuditEvent), key=lambda item: item.created_at)


@router.get("/compliance/exports")
async def compliance_export(
    runtime: MedChainRuntime = Depends(get_runtime),
    user: User = Depends(require_roles("platform_admin", "auditor")),
) -> dict[str, Any]:
    return await runtime.compliance_export(user)
