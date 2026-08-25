from datetime import datetime, timezone

import pytest

from app.ml.evaluation import binary_metrics, chronological_split
from app.ml.snapshots import build_manifest
from app.modules.scenarios.service import simulate_linear


def test_snapshot_is_deterministic_and_target_bound() -> None:
    rows = [{"date": "2025-01", "value": 1}]
    one = build_manifest(
        rows, {"event": "drought", "horizon_days": 30}, [{"source": "approved-test-v1"}]
    )
    two = build_manifest(
        rows, {"event": "drought", "horizon_days": 30}, [{"source": "approved-test-v1"}]
    )
    changed = build_manifest(
        rows, {"event": "drought", "horizon_days": 60}, [{"source": "approved-test-v1"}]
    )
    assert one.content_hash == two.content_hash
    assert one.content_hash != changed.content_hash


def test_split_is_chronological_not_random() -> None:
    dates = [datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2025, 1, 1, tzinfo=timezone.utc)]
    fold = chronological_split(dates, datetime(2024, 6, 1, tzinfo=timezone.utc))
    assert fold.train_indices == (0,)
    assert fold.test_indices == (1,)
    with pytest.raises(ValueError):
        chronological_split(dates, datetime(2023, 1, 1, tzinfo=timezone.utc))


def test_metrics_include_discrimination_calibration_and_high_risk_recall() -> None:
    metrics = binary_metrics([0, 1, 1, 0], [0.1, 0.8, 0.6, 0.4])
    assert metrics["recall"] == 1.0
    assert metrics["macro_f1"] == 1.0
    assert metrics["pr_auc"] == 1.0
    assert metrics["roc_auc"] == 1.0
    assert metrics["high_risk_recall"] == 0.5
    assert metrics["calibration_error"] is not None
    assert metrics["brier"] is not None
    assert 0 <= metrics["calibration_error"] <= 1
    assert 0 <= metrics["brier"] <= 1


def test_metrics_reject_invalid_probabilities_and_do_not_invent_auc() -> None:
    with pytest.raises(ValueError, match="between zero and one"):
        binary_metrics([0, 1], [0.1, 1.2])
    metrics = binary_metrics([1, 1], [0.8, 0.9])
    assert metrics["pr_auc"] is None
    assert metrics["roc_auc"] is None


def test_scenario_is_explicitly_non_publishable_simulation() -> None:
    result = simulate_linear(0.4, {"rainfall_reduction": 0.2, "price_increase": 0.1})
    assert result.label == "SIMULATION"
    assert result.simulated_score == 0.7
    assert result.may_publish_warning is False
