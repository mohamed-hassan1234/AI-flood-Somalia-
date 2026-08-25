from dataclasses import dataclass
from datetime import datetime

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


@dataclass(frozen=True)
class TemporalFold:
    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]


def chronological_split(timestamps: list[datetime], cutoff: datetime) -> TemporalFold:
    train = tuple(i for i, stamp in enumerate(timestamps) if stamp < cutoff)
    test = tuple(i for i, stamp in enumerate(timestamps) if stamp >= cutoff)
    if not train or not test:
        raise ValueError("Chronological split requires data on both sides of cutoff")
    if max(timestamps[i] for i in train) >= min(timestamps[i] for i in test):
        raise ValueError("Temporal leakage detected")
    return TemporalFold(train, test)


def binary_metrics(
    observed: list[int],
    probabilities: list[float],
    threshold: float = 0.5,
    high_risk_threshold: float = 0.7,
    calibration_bins: int = 10,
) -> dict[str, float | None]:
    if len(observed) != len(probabilities) or not observed:
        raise ValueError("Outcomes and probabilities must have equal non-zero length")
    if any(value not in {0, 1} for value in observed):
        raise ValueError("Observed outcomes must be binary")
    probability_array = np.asarray(probabilities, dtype=float)
    if not np.isfinite(probability_array).all() or np.any(
        (probability_array < 0) | (probability_array > 1)
    ):
        raise ValueError("Probabilities must be finite values between zero and one")
    if not 0 <= threshold <= 1 or not 0 <= high_risk_threshold <= 1:
        raise ValueError("Decision thresholds must be between zero and one")
    if calibration_bins < 2 or calibration_bins > 100:
        raise ValueError("Calibration bins must be between 2 and 100")
    observed_array = np.asarray(observed)
    predicted = (probability_array >= threshold).astype(int)
    high_risk = (probability_array >= high_risk_threshold).astype(int)
    calibration_error = 0.0
    edges = np.linspace(0, 1, calibration_bins + 1)
    for index in range(calibration_bins):
        in_bin = (probability_array >= edges[index]) & (
            probability_array < edges[index + 1]
            if index + 1 < calibration_bins
            else probability_array <= edges[index + 1]
        )
        if in_bin.any():
            calibration_error += float(in_bin.mean()) * abs(
                float(observed_array[in_bin].mean()) - float(probability_array[in_bin].mean())
            )
    both_classes = len(set(observed)) == 2
    return {
        "precision": float(precision_score(observed, predicted, zero_division=0)),
        "recall": float(recall_score(observed, predicted, zero_division=0)),
        "f1": float(f1_score(observed, predicted, zero_division=0)),
        "macro_f1": float(f1_score(observed, predicted, average="macro", zero_division=0)),
        "pr_auc": float(average_precision_score(observed, probabilities)) if both_classes else None,
        "roc_auc": float(roc_auc_score(observed, probabilities)) if both_classes else None,
        "brier": float(brier_score_loss(observed, probabilities)),
        "calibration_error": calibration_error,
        "high_risk_recall": float(recall_score(observed, high_risk, zero_division=0)),
    }
