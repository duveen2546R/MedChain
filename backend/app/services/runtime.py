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
    ValidationReport,
)
from ..security import contains_raw_patient_data
from ..store import Repository
from .aggregation import FedAvgAggregator
from .anomaly import AnomalyDetector
from .artifacts import ArtifactStore
from .audit import AuditService
from .blockchain import BlockchainService
from .evaluation import DigitalTwin
from .routing import RoutingService
from .validation import ModelUpdateValidator


class MedChainRuntime:
    """Coordinates rounds that receive real model updates from hospital clients."""

    def __init__(
        self,
        repo: Repository,
        settings: Settings,
        artifact_store: ArtifactStore | None = None,
        blockchain_service: BlockchainService | None = None,
    ):
        self.repo = repo
        self.settings = settings
        self.audit = AuditService(repo)
        self.artifacts = artifact_store or ArtifactStore(settings)
        self.blockchain = blockchain_service or BlockchainService(settings, repo)
        self.routing = RoutingService()
        self.twin = DigitalTwin.load(settings.digital_twin_path)
        self.validator = ModelUpdateValidator(settings, self.twin)
        self.anomaly = AnomalyDetector(settings)
        self.aggregator = FedAvgAggregator()
        self._submission_lock = asyncio.Lock()

    async def connect(self) -> None:
        await self.artifacts.connect()
        await self.blockchain.connect()

    async def close(self) -> None:
        await self.blockchain.close()
        await self.artifacts.close()

    async def register_hospital_on_chain(self, hospital_id: str, actor: User) -> Hospital:
        hospital = await self.repo.get("hospitals", hospital_id, Hospital)
        if hospital is None:
            raise ValueError("Hospital not found")
        if not hospital.wallet_address:
            raise ValueError("Hospital wallet_address is required")
        receipt = await self.blockchain.register_hospital(
            hospital.wallet_address,
            hospital.org_id,
            hospital.reputation,
        )
        hospital.blockchain_registered = True
        hospital.registry_tx_hash = receipt.registry_tx_hash or hospital.registry_tx_hash
        hospital.reputation_tx_hash = receipt.reputation_tx_hash or hospital.reputation_tx_hash
        await self.repo.put("hospitals", hospital)
        await self.audit.record(
            "hospital.blockchain.registered",
            "hospital",
            hospital.id,
            actor,
            {
                "wallet_address": hospital.wallet_address,
                "registry_tx_hash": receipt.registry_tx_hash,
                "reputation_tx_hash": receipt.reputation_tx_hash,
            },
        )
        return hospital

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
        all_submissions = await self.repo.list("submissions", Submission)
        running = current_round.status not in {"completed", "failed"} if current_round else False
        return DashboardSummary(
            hospitals=hospitals,
            versions=versions,
            round=current_round.round_number if current_round else 0,
            currentRoundId=current_round.id if current_round else None,
            currentRoundStatus=current_round.status if current_round else None,
            running=running,
            phase=current_round.phase if current_round else "No training round has been created",
            activeNode=current_round.active_node if current_round else None,
            submissionsReceived=len(submissions),
            submissionsRequired=len(current_round.selected_hospital_ids) if current_round else 0,
            evaluatedAccuracy=versions[-1].evaluated_accuracy if versions else None,
            rejectedSubmissions=sum(
                1 for submission in submissions if submission.status == "rejected"
            ),
            blockchainTransactions=sum(
                1 for submission in all_submissions if submission.blockchain_tx_hash
            ),
            blockchainChainId=self.blockchain.chain_id,
            blockchainConnected=self.blockchain.connected,
            blockchainSigner=self.blockchain.signer_address,
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
            latest_model = await self._latest_model_version()
            report = self.validator.validate(
                hospital,
                training_round,
                update,
                expected_dimension,
                global_weights=(latest_model.weights or None) if latest_model else None,
                global_evaluated_accuracy=(
                    latest_model.evaluated_accuracy / 100
                    if latest_model and latest_model.evaluated_accuracy is not None
                    else None
                ),
            )
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
                evaluated_accuracy=report.evaluated_accuracy,
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
                try:
                    await self._aggregate_round(training_round, submissions)
                except RuntimeError as exc:
                    training_round.status = "failed"
                    training_round.active_node = None
                    training_round.phase = (
                        f"Round {training_round.round_number} blockchain recording failed: {exc}"
                    )
                    await self.repo.put("rounds", training_round)
                    await self.audit.record(
                        "round.blockchain.failed",
                        "round",
                        training_round.id,
                        metadata={"error": str(exc)},
                    )
            return submission

    async def cancel_round(self, round_id: str, actor: User) -> TrainingRound:
        training_round = await self.repo.get("rounds", round_id, TrainingRound)
        if training_round is None:
            raise ValueError("Training round not found")
        if training_round.status in {"completed", "failed"}:
            raise ValueError("Only an in-flight training round can be cancelled")
        training_round.status = "failed"
        training_round.active_node = None
        training_round.phase = f"Round {training_round.round_number} cancelled by administrator"
        await self.repo.put("rounds", training_round)
        for hospital in await self.repo.list("hospitals", Hospital):
            if hospital.status != "idle":
                hospital.status = "idle"
                await self.repo.put("hospitals", hospital)
        await self.audit.record("round.cancelled", "round", round_id, actor)
        return training_round

    async def retry_round_blockchain(self, round_id: str, actor: User) -> TrainingRound:
        training_round = await self.repo.get("rounds", round_id, TrainingRound)
        if training_round is None:
            raise ValueError("Training round not found")
        submissions = await self.repo.list("submissions", Submission, round_id=round_id)
        if len(submissions) != len(training_round.selected_hospital_ids):
            raise ValueError("The round has not received every selected hospital update")
        await self._aggregate_round(training_round, submissions)
        await self.audit.record("round.blockchain.retried", "round", round_id, actor)
        return training_round

    async def run_inference(self, features: list[float], actor: User) -> dict[str, Any]:
        if self.twin is None:
            raise RuntimeError("Digital twin is not configured; inference is unavailable")
        model = await self._latest_model_version()
        if model is None or not model.weights:
            raise LookupError("No evaluated global model is available yet - run a training round")

        probability = self.twin.predict_proba(features, model.weights)
        confidence = max(probability, 1 - probability)
        if confidence >= 0.9:
            tier = "high"
        elif confidence >= self.settings.inference_low_confidence:
            tier = "moderate"
        else:
            tier = "low"
        consultation = confidence < self.settings.inference_low_confidence

        # Audit derived values only; clinical feature vectors never reach the log.
        await self.audit.record(
            "inference.performed",
            "model_version",
            model.id,
            actor,
            {
                "model_version": model.version,
                "confidence_tier": tier,
                "specialist_consultation_recommended": consultation,
            },
        )
        return {
            "prediction": "benign" if probability >= 0.5 else "malignant",
            "probability": round(probability, 4),
            "confidence": round(confidence, 4),
            "confidence_tier": tier,
            "specialist_consultation_recommended": consultation,
            "model_version": model.version,
            "evaluated_accuracy": model.evaluated_accuracy,
        }

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

    async def _latest_model_version(self) -> ModelVersion | None:
        versions = sorted(await self.repo.list("model_versions", ModelVersion), key=lambda item: item.round)
        return versions[-1] if versions else None

    async def _demote_anomalous_submissions(
        self,
        training_round: TrainingRound,
        verified: list[Submission],
    ) -> list[Submission]:
        flagged = self.anomaly.flag_outliers(
            [(submission.hospital_id, submission.weights) for submission in verified]
        )
        if not flagged:
            return verified
        for submission in verified:
            reasons = flagged.get(submission.hospital_id)
            if not reasons:
                continue
            submission.status = "rejected"
            report = ValidationReport(
                round_id=training_round.id,
                hospital_id=submission.hospital_id,
                passed=False,
                score=submission.evaluated_accuracy or 0,
                reasons=reasons,
                evaluated_accuracy=submission.evaluated_accuracy,
                stage="aggregation",
            )
            await self.repo.put("validation_reports", report)
            submission.validation_report_id = report.id
            await self.repo.put("submissions", submission)
            if submission.hospital_id in training_round.contributor_ids:
                training_round.contributor_ids.remove(submission.hospital_id)
            if submission.hospital_id not in training_round.rejected_hospital_ids:
                training_round.rejected_hospital_ids.append(submission.hospital_id)
            hospital = await self.repo.get("hospitals", submission.hospital_id, Hospital)
            if hospital is not None:
                hospital.status = "rejected"
                await self.repo.put("hospitals", hospital)
            await self.audit.record(
                "round.submission.anomaly_rejected",
                "submission",
                submission.id,
                metadata={"round_id": training_round.id, "reasons": reasons},
            )
        await self.repo.put("rounds", training_round)
        return [submission for submission in verified if submission.hospital_id not in flagged]

    async def _aggregate_round(
        self,
        training_round: TrainingRound,
        submissions: list[Submission],
    ) -> None:
        verified = [submission for submission in submissions if submission.status == "verified"]
        verified = await self._demote_anomalous_submissions(training_round, verified)
        if not verified:
            await self._record_submissions_on_chain(training_round, submissions, "no-model")
            await self._apply_reputation(training_round, submissions)
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
        evaluated_accuracy: float | None = None
        if self.twin is not None:
            twin_accuracy, _ = self.twin.evaluate(weights)
            evaluated_accuracy = round(twin_accuracy * 100, 2)
        metric_source = (
            "digital_twin_evaluation" if evaluated_accuracy is not None else "weighted_client_report"
        )
        artifact_uri, model_hash = await self.artifacts.put_json(
            "models",
            {
                "round_id": training_round.id,
                "weights": weights,
                "contributors": training_round.contributor_ids,
                "evaluated_accuracy": evaluated_accuracy,
                "metric_source": metric_source,
            },
        )
        model_version = f"v{training_round.round_number}"
        await self._record_submissions_on_chain(
            training_round,
            submissions,
            model_version,
        )
        await self._apply_reputation(training_round, submissions)
        existing_model = await self.repo.find_one(
            "model_versions", ModelVersion, round=training_round.round_number
        )
        model = existing_model or await self.repo.put(
            "model_versions",
            ModelVersion(
                version=model_version,
                round=training_round.round_number,
                accuracy=reported_accuracy,
                evaluated_accuracy=evaluated_accuracy,
                contributors=len(verified),
                artifact_uri=artifact_uri,
                model_hash=model_hash,
                weights=weights,
                metric_source=metric_source,
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

    async def _apply_reputation(
        self,
        training_round: TrainingRound,
        submissions: list[Submission],
    ) -> None:
        if training_round.reputation_applied:
            return
        for submission in submissions:
            hospital = await self.repo.get("hospitals", submission.hospital_id, Hospital)
            if hospital is None or not hospital.wallet_address or not hospital.blockchain_registered:
                continue
            verified = submission.status == "verified"
            delta = self.settings.reputation_reward if verified else -self.settings.reputation_penalty
            reason = "verified_contribution" if verified else "rejected_contribution"
            receipt, score = await self.blockchain.update_reputation(
                hospital.wallet_address,
                delta,
                reason,
                training_round.id,
            )
            if score == hospital.reputation and receipt is None:
                continue
            hospital.reputation = score
            await self.repo.put("hospitals", hospital)
            await self.audit.record(
                "hospital.reputation.updated",
                "hospital",
                hospital.id,
                metadata={
                    "round_id": training_round.id,
                    "delta": delta,
                    "score": score,
                    "reason": reason,
                    "tx_hash": receipt.tx_hash if receipt else None,
                },
            )
        training_round.reputation_applied = True
        await self.repo.put("rounds", training_round)

    async def _record_submissions_on_chain(
        self,
        training_round: TrainingRound,
        submissions: list[Submission],
        model_version: str,
    ) -> None:
        for submission in submissions:
            if submission.blockchain_tx_hash:
                continue
            hospital = await self.repo.get("hospitals", submission.hospital_id, Hospital)
            if hospital is None or not hospital.wallet_address or not hospital.blockchain_registered:
                raise RuntimeError(
                    f"Hospital {submission.hospital_id} is not registered on-chain"
                )
            receipt = await self.blockchain.record_contribution(
                round_id=training_round.id,
                model_version=model_version,
                contributor=hospital.wallet_address,
                update_hash=submission.update_hash,
                artifact_uri=submission.artifact_uri,
                validated=submission.status == "verified",
            )
            submission.blockchain_tx_hash = receipt.tx_hash
            submission.blockchain_block_number = receipt.block_number
            await self.repo.put("submissions", submission)
            await self.audit.record(
                "round.submission.recorded_on_chain",
                "submission",
                submission.id,
                metadata={
                    "tx_hash": receipt.tx_hash,
                    "block_number": receipt.block_number,
                },
            )

    @staticmethod
    def _dump(model: Any) -> dict[str, Any]:
        if hasattr(model, "model_dump"):
            return model.model_dump(mode="json")
        return json.loads(model.json())
