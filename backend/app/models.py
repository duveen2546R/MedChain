from __future__ import annotations

from datetime import UTC, datetime
import secrets
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def new_token() -> str:
    return secrets.token_urlsafe(32)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def utcnow() -> datetime:
    return datetime.now(UTC)


Role = Literal[
    "platform_admin",
    "hospital_admin",
    "hospital_node",
    "clinic_user",
    "auditor",
    "research_partner",
]

HospitalStatus = Literal["idle", "training", "submitted", "validated", "rejected"]
RoundStatus = Literal["routing", "training", "validating", "aggregating", "completed", "failed"]
SubmissionStatus = Literal["submitted", "verified", "rejected"]


class APIModel(BaseModel):
    model_config = ConfigDict(use_enum_values=True, populate_by_name=True, allow_inf_nan=False)


class Organization(APIModel):
    id: str = Field(default_factory=lambda: new_id("org"))
    name: str
    type: Literal["hospital", "clinic", "platform", "research", "government"]
    tier: Literal["clinic", "consortium_node", "internal", "partner"] = "clinic"
    created_at: datetime = Field(default_factory=utcnow)


class User(APIModel):
    id: str = Field(default_factory=lambda: new_id("usr"))
    email: str
    name: str
    role: Role
    org_id: str
    password_hash: str
    active: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class AccessRequest(APIModel):
    id: str = Field(default_factory=lambda: new_id("req"))
    organization_name: str
    organization_type: Literal["hospital", "research"]
    contact_name: str
    email: str
    message: str = ""
    status: Literal["pending", "approved", "rejected"] = "pending"
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    org_id: str | None = None
    invitation_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Invitation(APIModel):
    id: str = Field(default_factory=lambda: new_id("inv"))
    token: str = Field(default_factory=new_token)
    email: str
    role: Role
    org_id: str
    invited_by: str
    expires_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class PasswordResetToken(APIModel):
    id: str = Field(default_factory=lambda: new_id("prt"))
    token: str = Field(default_factory=new_token)
    user_id: str
    expires_at: datetime
    used_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Hospital(APIModel):
    id: str
    org_id: str
    name: str
    region: str
    samples: int
    specialty: str
    reputation: int = 80
    status: HospitalStatus = "idle"
    contribution: float = 0
    active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    wallet_address: str | None = None
    blockchain_registered: bool = False
    registry_tx_hash: str | None = None
    reputation_tx_hash: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class TrainingObjective(APIModel):
    id: str = Field(default_factory=lambda: new_id("obj"))
    name: str
    disease_category: str
    specialty: str
    target_metric: str = "accuracy"
    target_value: float = 0.9
    min_participants: int = 3
    routing_metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class TrainingRound(APIModel):
    id: str = Field(default_factory=lambda: new_id("rnd"))
    objective_id: str
    round_number: int
    status: RoundStatus = "routing"
    selected_hospital_ids: list[str] = Field(default_factory=list)
    contributor_ids: list[str] = Field(default_factory=list)
    rejected_hospital_ids: list[str] = Field(default_factory=list)
    phase: str = "Routing hospitals"
    active_node: str | None = None
    reputation_applied: bool = False
    started_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None


class ModelUpdate(APIModel):
    weights: list[float] = Field(min_length=1, max_length=100_000)
    metrics: dict[str, float]
    schema_version: str = "medchain-update-v1"


class Submission(APIModel):
    id: str = Field(default_factory=lambda: new_id("sub"))
    round_id: str
    hospital_id: str
    artifact_uri: str
    update_hash: str
    weights: list[float]
    status: SubmissionStatus = "submitted"
    metrics: dict[str, float] = Field(default_factory=dict)
    evaluated_accuracy: float | None = None
    validation_report_id: str | None = None
    blockchain_tx_hash: str | None = None
    blockchain_block_number: int | None = None
    submitted_at: datetime = Field(default_factory=utcnow)


class ValidationReport(APIModel):
    id: str = Field(default_factory=lambda: new_id("val"))
    round_id: str
    hospital_id: str
    passed: bool
    score: float
    reasons: list[str] = Field(default_factory=list)
    evaluated_accuracy: float | None = None
    evaluated_loss: float | None = None
    checks: dict[str, Any] = Field(default_factory=dict)
    stage: Literal["submission", "aggregation"] = "submission"
    created_at: datetime = Field(default_factory=utcnow)


class ModelVersion(APIModel):
    id: str = Field(default_factory=lambda: new_id("mdl"))
    version: str
    round: int
    accuracy: float
    evaluated_accuracy: float | None = None
    contributors: int
    artifact_uri: str
    model_hash: str
    weights: list[float] = Field(default_factory=list)
    metric_source: str = "weighted_client_report"
    created_at: datetime = Field(default_factory=utcnow)


class AuditEvent(APIModel):
    id: str = Field(default_factory=lambda: new_id("aud"))
    actor_id: str | None
    actor_role: str | None
    action: str
    resource_type: str
    resource_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)


class ComplianceExport(APIModel):
    id: str = Field(default_factory=lambda: new_id("exp"))
    requested_by: str
    format: Literal["json"] = "json"
    audit_event_count: int
    created_at: datetime = Field(default_factory=utcnow)


class DashboardSummary(APIModel):
    hospitals: list[Hospital]
    versions: list[ModelVersion]
    round: int
    currentRoundId: str | None = None
    currentRoundStatus: RoundStatus | None = None
    running: bool
    phase: str
    activeNode: str | None = None
    submissionsReceived: int = 0
    submissionsRequired: int = 0
    evaluatedAccuracy: float | None = None
    rejectedSubmissions: int = 0
    blockchainTransactions: int = 0
    blockchainChainId: int | None = None
    blockchainConnected: bool = False
    blockchainSigner: str | None = None
