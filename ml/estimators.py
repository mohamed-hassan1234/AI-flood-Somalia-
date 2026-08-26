"""Stable, importable estimators used in serialized Phase 02 artifacts."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin


def baseline_probability(track: str, frame: pd.DataFrame, prevalence: float) -> np.ndarray:
    if track == "drought":
        rain_signal = np.clip((15.0 - frame["rain_30d_mm"].fillna(15.0)) / 30.0, -1, 1)
        wet_signal = np.clip((0.35 - frame["gwet_top_30d"].fillna(0.35)) / 0.25, -1, 1)
        veg_signal = np.clip((0.20 - frame["ndvi_last"].fillna(0.20)) / 0.15, -1, 1)
        score = -1.6 + 1.0 * rain_signal + 0.8 * wet_signal + 0.7 * veg_signal
        return np.asarray(1 / (1 + np.exp(-score)), dtype=float)
    if track == "flood":
        ratio = frame["level_ratio_moderate"].fillna(0.0)
        rise = frame["level_change_3d"].fillna(0.0)
        rain = frame["rain_7d_mm"].fillna(0.0)
        score = -3.5 + 5.0 * ratio + 1.2 * np.clip(rise, -1, 2) + 0.015 * np.clip(rain, 0, 100)
        return np.asarray(1 / (1 + np.exp(-score)), dtype=float)
    previous = frame["previous_ipc3plus_percentage"]
    probability = np.clip(previous / 0.40, 0.02, 0.98)
    return probability.fillna(prevalence).to_numpy(dtype=float)


class RuleEstimator(ClassifierMixin, BaseEstimator):
    """Serializable, deterministic operational baseline."""

    def __init__(self, track: str):
        self.track = track
        self.prevalence = 0.5

    def fit(self, frame: pd.DataFrame, target: pd.Series) -> "RuleEstimator":
        self.prevalence = float(np.mean(target))
        self.classes_ = np.array([0, 1])
        return self

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        positive = baseline_probability(self.track, frame, self.prevalence)
        positive = np.clip(np.asarray(positive, dtype=float), 0.0, 1.0)
        return np.column_stack([1.0 - positive, positive])
