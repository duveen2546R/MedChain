from __future__ import annotations

from backend.app.config import Settings
from backend.app.services.anomaly import AnomalyDetector

TEST_SECRET = "test-secret-key-that-is-longer-than-thirty-two-characters"


def detector() -> AnomalyDetector:
    return AnomalyDetector(Settings(secret_key=TEST_SECRET))


def test_fewer_than_three_entries_are_not_screened() -> None:
    assert detector().flag_outliers([("h1", [1.0, 0.0]), ("h2", [-1.0, 0.0])]) == {}


def test_opposing_update_is_flagged() -> None:
    flagged = detector().flag_outliers(
        [
            ("h1", [1.0, 0.1, 0.0]),
            ("h2", [1.1, 0.05, 0.02]),
            ("h3", [0.95, 0.08, -0.01]),
            ("h4", [-1.0, -0.1, 0.0]),
        ]
    )
    assert set(flagged) == {"h4"}
    assert any("consensus" in reason for reason in flagged["h4"])


def test_aligned_updates_pass() -> None:
    flagged = detector().flag_outliers(
        [
            ("h1", [1.0, 0.1]),
            ("h2", [1.05, 0.12]),
            ("h3", [0.98, 0.09]),
        ]
    )
    assert flagged == {}
