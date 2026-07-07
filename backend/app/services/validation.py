from __future__ import annotations

import math

from ..config import Settings
from ..models import Hospital, ModelUpdate, TrainingRound, ValidationReport
from .evaluation import DigitalTwin


class ModelUpdateValidator:
    """Schema checks plus the digital-twin sandbox gate for every model update."""

    def __init__(self, settings: Settings, twin: DigitalTwin | None = None):
        self.settings = settings
        self.twin = twin

    def validate(
        self,
        hospital: Hospital,
        training_round: TrainingRound,
        update: ModelUpdate,
        expected_dimension: int | None = None,
        global_weights: list[float] | None = None,
        global_evaluated_accuracy: float | None = None,
        twin: DigitalTwin | None = None,
    ) -> ValidationReport:
        # Per-objective twin when provided; otherwise the validator's default (global) twin.
        twin = twin if twin is not None else self.twin
        reasons: list[str] = []
        checks: dict[str, object] = {}
        if update.schema_version != "medchain-update-v1":
            reasons.append("Unsupported model-update schema")

        if twin is not None:
            expected_dimension = twin.expected_dimension
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

        evaluated_accuracy: float | None = None
        evaluated_loss: float | None = None
        if twin is not None and not reasons:
            evaluated_accuracy, evaluated_loss = twin.evaluate(update.weights)
            checks["digital_twin_accuracy"] = round(evaluated_accuracy, 4)
            checks["digital_twin_loss"] = round(evaluated_loss, 4)

            if evaluated_accuracy < self.settings.twin_floor_accuracy:
                reasons.append(
                    "Digital-twin stress test failed: evaluated accuracy "
                    f"{evaluated_accuracy:.2f} is below the {self.settings.twin_floor_accuracy:.2f} floor"
                )
            if (
                global_evaluated_accuracy is not None
                and evaluated_accuracy
                < global_evaluated_accuracy - self.settings.twin_regression_tolerance
            ):
                reasons.append(
                    "Digital-twin stress test failed: update degrades the global model "
                    f"({evaluated_accuracy:.2f} vs {global_evaluated_accuracy:.2f})"
                )

            if global_weights and len(global_weights) == len(update.weights):
                distance = math.dist(update.weights, global_weights)
                checks["distance_from_global"] = round(distance, 4)
                if distance > self.settings.anomaly_distance_cap:
                    reasons.append(
                        f"Update magnitude anomaly: distance from the global model {distance:.2f} "
                        f"exceeds the {self.settings.anomaly_distance_cap:.2f} cap"
                    )

            if 0 <= accuracy <= 1:
                divergence = abs(accuracy - evaluated_accuracy)
                checks["reported_metric_divergence"] = round(divergence, 4)
                if divergence > self.settings.reported_metric_tolerance:
                    reasons.append(
                        "Implausible reported metrics: local_accuracy diverges from the "
                        f"digital-twin evaluation by {divergence:.2f}"
                    )

        score = evaluated_accuracy if evaluated_accuracy is not None else (
            accuracy if 0 <= accuracy <= 1 else 0
        )
        return ValidationReport(
            round_id=training_round.id,
            hospital_id=hospital.id,
            passed=not reasons,
            score=round(score, 4),
            reasons=reasons,
            evaluated_accuracy=None if evaluated_accuracy is None else round(evaluated_accuracy, 4),
            evaluated_loss=None if evaluated_loss is None else round(evaluated_loss, 4),
            checks=checks,
        )
