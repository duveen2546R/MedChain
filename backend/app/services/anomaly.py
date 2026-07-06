from __future__ import annotations

import numpy as np

from ..config import Settings


class AnomalyDetector:
    """Cross-client poisoning screen run over a round's verified updates."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def flag_outliers(self, entries: list[tuple[str, list[float]]]) -> dict[str, list[str]]:
        """Return {entry_id: reasons} for updates that deviate from the round consensus."""
        if len(entries) < 3:
            return {}

        matrix = np.asarray([weights for _, weights in entries], dtype=np.float64)
        reference = np.median(matrix, axis=0)
        flagged: dict[str, list[str]] = {}

        distances = np.linalg.norm(matrix - reference, axis=1)
        median_distance = float(np.median(distances))
        mad = float(np.median(np.abs(distances - median_distance)))
        for index, ((entry_id, _), distance) in enumerate(zip(entries, distances)):
            reasons: list[str] = []
            if mad > 1e-12:
                z_score = 0.6745 * (distance - median_distance) / mad
                if z_score > self.settings.anomaly_mad_threshold:
                    reasons.append(
                        f"Update deviates from the round consensus (modified z-score {z_score:.2f})"
                    )
            row = matrix[index]
            row_norm = float(np.linalg.norm(row))
            reference_norm = float(np.linalg.norm(reference))
            if row_norm > 1e-12 and reference_norm > 1e-12:
                cosine = float(row @ reference) / (row_norm * reference_norm)
                if cosine < 0:
                    reasons.append(
                        f"Update direction opposes the round consensus (cosine similarity {cosine:.2f})"
                    )
            if reasons:
                flagged[entry_id] = reasons
        return flagged
