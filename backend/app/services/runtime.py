from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from ..config import Settings
from ..models import (
    AuditEvent,
    ComplianceExport,
    DashboardSummary,
    Hospital,
    ModelUpdate,
    ModelVersion,
    Submission,
    TrainingObjective,
    TrainingRound,
    User,
)
from ..security import contains_raw_patient_data
from ..store import Repository
from .aggregation import FedAvgAggregator
from .artifacts import ArtifactStore
from .audit import AuditService
from .routing import RoutingService
from .validation import ModelUpdateValidator


class MedChainRuntime:
    """Coordinates rounds that receive real model updates from hospital clients."""

    def __init__(
        self,
        repo: Repository,
        settings: Settings,
        artifact_store: ArtifactStore | None = None,
    ):
        self.repo = repo
        self.settings = settings
        self.audit = AuditService(repo)
        self.artifacts = artifact_store or ArtifactStore(settings)
        self.routing = RoutingService()
        self.validator = ModelUpdateValidator()
        self.aggregator = FedAvgAggregator()
        self._submission_lock = asyncio.Lock()

    async def connect(self) -> None:
        await self.artifacts.connect()

    async def close(self) -> None:
        await self.artifacts.close()

    async def dashboard_summary(self) -> DashboardSummary:
        hospitals = sorted(await self.repo.list("hospitals", Hospital), key=lambda item: item.id)
        versions = sorted(await self.repo.list("model_versions", ModelVersion), key=lambda item: item.round)
        rounds = sorted(await self.repo.list("rounds", TrainingRound), key=lambda item: item.round_number)
        current_round = rounds[-1] if rounds else None
        submissions = (
            await self.repo.list("submissions", Submission, round_id=current_round.id)
            if current_round
            else []
        )
        running = current_round.status not in {"completed", "failed"} if current_round else False
        return DashboardSummary(
            hospitals=hospitals,
            versions=versions,
            round=current_round.round_number if current_round else 0,
            running=running,
            phase=current_round.phase if current_round else "No training round has been created",
            activeNode=current_round.active_node if current_round else None,
            submissionsReceived=len(submissions),
            submissionsRequired=len(current_round.selected_hospital_ids) if current_round else 0,
        )

    async def create_objective(self, objective: TrainingObjective, actor: User) -> TrainingObjective:
        objective.created_by = actor.id
        saved = await self.repo.put("training_objectives", objective)
        await self.audit.record("training_objective.created", "training_objective", saved.id, actor)
        return saved

    async def create_round(self, objective_id: str | None, actor: User) -> TrainingRound:
        rounds = sorted(await self.repo.list("rounds", TrainingRound), key=lambda item: item.round_number)
        if rounds and rounds[-1].status not in {"completed", "failed"}:
            raise ValueError("A training round is already active")

        if objective_id:
            objective = await self.repo.get("training_objectives", objective_id, TrainingObjective)
            if objective is None:
                raise ValueError("Training objective not found")
        else:
            objectives = sorted(
                await self.repo.list("training_objectives", TrainingObjective),
                key=lambda item: item.created_at,
            )
            if not objectives:
                raise ValueError("Create a training objective before starting a round")
            objective = objectives[-1]

        hospitals = await self.repo.list("hospitals", Hospital)
        selected = self.routing.select_hospitals(objective, hospitals)
        if len(selected) < objective.min_participants:
            raise ValueError(
                f"Objective requires {objective.min_participants} active hospitals; only {len(selected)} are available"
            )

        training_round = TrainingRound(
            objective_id=objective.id,
            round_number=len(rounds) + 1,
            status="training",
            selected_hospital_ids=[hospital.id for hospital in selected],
            phase=f"Round {len(rounds) + 1} awaiting {len(selected)} hospital model updates",
        )
        await self.repo.put("rounds", training_round)
        for hospital in hospitals:
            hospital.status = "training" if hospital.id in training_round.selected_hospital_ids else "idle"
            hospital.contribution = 0
            await self.repo.put("hospitals", hospital)
        await self.audit.record(
            "round.created",
            "round",
            training_round.id,
            actor,
            {"objective_id": objective.id, "selected_hospitals": training_round.selected_hospital_ids},
        )
        return training_round

    async def submit_external_update(
        self,
        round_id: str,
        hospital_id: str,
        payload: dict[str, Any],
        actor: User,
    ) -> Submission:
        if contains_raw_patient_data(payload):
            raise ValueError("Raw patient data is not accepted by model-update endpoints")

        async with self._submission_lock:
            training_round = await self.repo.get("rounds", round_id, TrainingRound)
            hospital = await self.repo.get("hospitals", hospital_id, Hospital)
            if training_round is None or hospital is None:
                raise ValueError("Unknown training round or hospital")
            if training_round.status not in {"training", "validating"}:
                raise ValueError("This training round is not accepting updates")
            if hospital.id not in training_round.selected_hospital_ids:
                raise ValueError("Hospital was not selected for this training round")
            if actor.org_id != hospital.org_id:
                raise PermissionError("Users may only submit updates for their own organization")
            if await self.repo.find_one(
                "submissions", Submission, round_id=training_round.id, hospital_id=hospital.id
            ):
                raise ValueError("Hospital has already submitted an update for this round")

            try:
                update = ModelUpdate(**payload)
            except ValidationError as exc:
                raise ValueError(f"Invalid model update: {exc.errors()[0]['msg']}") from exc
            prior_verified = await self.repo.list(
                "submissions", Submission, round_id=training_round.id, status="verified"
            )
            expected_dimension = len(prior_verified[0].weights) if prior_verified else None
            report = self.validator.validate(hospital, training_round, update, expected_dimension)
            await self.repo.put("validation_reports", report)

            artifact_uri, update_hash = await self.artifacts.put_json(
                "updates",
                {"round_id": training_round.id, "hospital_id": hospital.id, "update": self._dump(update)},
            )
            submission = Submission(
                round_id=training_round.id,
                hospital_id=hospital.id,
                artifact_uri=artifact_uri,
                update_hash=update_hash,
                weights=update.weights,
                metrics=update.metrics,
                status="verified" if report.passed else "rejected",
                validation_report_id=report.id,
            )
            await self.repo.put("submissions", submission)

            if report.passed:
                hospital.status = "validated"
                training_round.contributor_ids.append(hospital.id)
            else:
                hospital.status = "rejected"
                training_round.rejected_hospital_ids.append(hospital.id)
            training_round.status = "validating"
            training_round.active_node = hospital.id
            await self.repo.put("hospitals", hospital)

            submissions = await self.repo.list("submissions", Submission, round_id=training_round.id)
            training_round.phase = (
                f"Round {training_round.round_number} received {len(submissions)}/"
                f"{len(training_round.selected_hospital_ids)} model updates"
            )
            await self.repo.put("rounds", training_round)
            await self.audit.record(
                "round.submission.received",
                "submission",
                submission.id,
                actor,
                {"round_id": round_id, "hospital_id": hospital_id, "status": submission.status},
            )

            if len(submissions) == len(training_round.selected_hospital_ids):
                await self._aggregate_round(training_round, submissions)
            return submission

    async def current_model(self) -> ModelVersion:
        versions = sorted(await self.repo.list("model_versions", ModelVersion), key=lambda item: item.round)
        if not versions:
            raise ValueError("No aggregated model is available")
        return versions[-1]

    async def compliance_export(self, actor: User) -> dict[str, Any]:
        audit_events = await self.repo.list("audit_events", AuditEvent)
        export = await self.repo.put(
            "compliance_exports",
            ComplianceExport(requested_by=actor.id, audit_event_count=len(audit_events)),
        )
        await self.audit.record("compliance.exported", "compliance_export", export.id, actor)
        return {
            "export": self._dump(export),
            "audit_events": [self._dump(event) for event in audit_events],
        }

    async def _aggregate_round(
        self,
        training_round: TrainingRound,
        submissions: list[Submission],
    ) -> None:
        verified = [submission for submission in submissions if submission.status == "verified"]
        if not verified:
            training_round.status = "failed"
            training_round.active_node = None
            training_round.phase = f"Round {training_round.round_number} failed: no valid model updates"
            await self.repo.put("rounds", training_round)
            return

        updates: list[tuple[Hospital, ModelUpdate]] = []
        for submission in verified:
            hospital = await self.repo.get("hospitals", submission.hospital_id, Hospital)
            if hospital is None:
                raise RuntimeError(f"Hospital {submission.hospital_id} no longer exists")
            updates.append(
                (
                    hospital,
                    ModelUpdate(weights=submission.weights, metrics=submission.metrics),
                )
            )

        training_round.status = "aggregating"
        training_round.active_node = None
        training_round.phase = f"Round {training_round.round_number} aggregating verified model updates"
        await self.repo.put("rounds", training_round)

        weights, reported_accuracy = self.aggregator.aggregate(updates)
        artifact_uri, model_hash = await self.artifacts.put_json(
            "models",
            {
                "round_id": training_round.id,
                "weights": weights,
                "contributors": training_round.contributor_ids,
                "metric_source": "weighted_client_report",
            },
        )
        model = await self.repo.put(
            "model_versions",
            ModelVersion(
                version=f"v{training_round.round_number}",
                round=training_round.round_number,
                accuracy=reported_accuracy,
                contributors=len(verified),
                artifact_uri=artifact_uri,
                model_hash=model_hash,
            ),
        )

        total_samples = sum(submission.metrics["samples"] for submission in verified)
        hospitals = await self.repo.list("hospitals", Hospital)
        submissions_by_hospital = {submission.hospital_id: submission for submission in verified}
        for hospital in hospitals:
            submission = submissions_by_hospital.get(hospital.id)
            hospital.contribution = (
                round(submission.metrics["samples"] / total_samples * 100, 2) if submission else 0
            )
            hospital.status = "idle"
            await self.repo.put("hospitals", hospital)

        training_round.status = "completed"
        training_round.completed_at = datetime.now(UTC)
        training_round.phase = (
            f"Round {training_round.round_number} complete - {model.version} aggregated from "
            f"{len(verified)} verified client updates"
        )
        await self.repo.put("rounds", training_round)

    @staticmethod
    def _dump(model: Any) -> dict[str, Any]:
        if hasattr(model, "model_dump"):
            return model.model_dump(mode="json")
        return json.loads(model.json())
