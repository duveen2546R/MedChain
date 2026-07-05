from __future__ import annotations

from ..models import Hospital, ModelUpdate, TrainingRound, ValidationReport


class ModelUpdateValidator:
    def validate(
        self,
        hospital: Hospital,
        training_round: TrainingRound,
        update: ModelUpdate,
        expected_dimension: int | None = None,
    ) -> ValidationReport:
        reasons: list[str] = []
        if update.schema_version != "medchain-update-v1":
            reasons.append("Unsupported model-update schema")
        if expected_dimension is not None and len(update.weights) != expected_dimension:
            reasons.append(f"Expected {expected_dimension} weights, received {len(update.weights)}")

        required_metrics = {"local_accuracy", "loss", "samples"}
        missing = sorted(required_metrics.difference(update.metrics))
        if missing:
            reasons.append(f"Missing metrics: {', '.join(missing)}")

        accuracy = update.metrics.get("local_accuracy", -1)
        loss = update.metrics.get("loss", -1)
        samples = update.metrics.get("samples", 0)
        if not 0 <= accuracy <= 1:
            reasons.append("local_accuracy must be between 0 and 1")
        if loss < 0:
            reasons.append("loss must be non-negative")
        if not 0 < samples <= hospital.samples:
            reasons.append("samples must be positive and no greater than the hospital dataset size")

        score = accuracy if 0 <= accuracy <= 1 else 0
        return ValidationReport(
            round_id=training_round.id,
            hospital_id=hospital.id,
            passed=not reasons,
            score=round(score, 4),
            reasons=reasons,
        )
