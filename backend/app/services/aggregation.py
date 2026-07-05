from __future__ import annotations

from ..models import Hospital, ModelUpdate


class FedAvgAggregator:
    def aggregate(
        self,
        updates: list[tuple[Hospital, ModelUpdate]],
    ) -> tuple[list[float], float]:
        if not updates:
            raise ValueError("At least one verified model update is required")

        dimensions = {len(update.weights) for _, update in updates}
        if len(dimensions) != 1:
            raise ValueError("Verified model updates have inconsistent dimensions")

        total_samples = sum(update.metrics["samples"] for _, update in updates)
        weights = [0.0] * len(updates[0][1].weights)
        weighted_accuracy = 0.0
        for hospital, update in updates:
            factor = update.metrics["samples"] / total_samples
            for index, weight in enumerate(update.weights):
                weights[index] += weight * factor
            weighted_accuracy += update.metrics["local_accuracy"] * factor

        return [round(weight, 8) for weight in weights], round(weighted_accuracy * 100, 2)
