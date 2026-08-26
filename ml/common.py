from __future__ import annotations

import hashlib
import json
import math
import platform
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import BaseEstimator
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


RANDOM_SEED = 20260826


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    compression = "gzip" if path.suffix == ".gz" else None
    frame.to_csv(temporary, index=False, compression=compression)
    temporary.replace(path)


def finite_or_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: finite_or_none(item) for key, item in value.items()}
    if isinstance(value, list):
        return [finite_or_none(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def expected_calibration_error(y: np.ndarray, probability: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = len(y)
    result = 0.0
    for index in range(bins):
        if index == bins - 1:
            mask = (probability >= edges[index]) & (probability <= edges[index + 1])
        else:
            mask = (probability >= edges[index]) & (probability < edges[index + 1])
        if mask.any():
            result += mask.mean() * abs(float(y[mask].mean()) - float(probability[mask].mean()))
    return float(result) if total else float("nan")


def metrics(y: np.ndarray, probability: np.ndarray, threshold: float) -> dict[str, Any]:
    y = np.asarray(y, dtype=int)
    probability = np.clip(np.asarray(probability, dtype=float), 0.0, 1.0)
    prediction = (probability >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, prediction, labels=[0, 1]).ravel()
    prevalence = float(y.mean()) if len(y) else float("nan")
    return finite_or_none(
        {
            "rows": len(y),
            "positives": int(y.sum()),
            "negatives": int((1 - y).sum()),
            "prevalence": prevalence,
            "accuracy": accuracy_score(y, prediction),
            "balanced_accuracy": balanced_accuracy_score(y, prediction),
            "precision": precision_score(y, prediction, zero_division=0),
            "recall": recall_score(y, prediction, zero_division=0),
            "f1": f1_score(y, prediction, zero_division=0),
            "roc_auc": roc_auc_score(y, probability) if len(np.unique(y)) == 2 else None,
            "pr_auc": average_precision_score(y, probability) if y.sum() else None,
            "brier": brier_score_loss(y, probability),
            "ece_10_bin": expected_calibration_error(y, probability),
            "false_alarm_rate": fp / (fp + tn) if fp + tn else None,
            "miss_rate": fn / (fn + tp) if fn + tp else None,
            "true_negative": int(tn),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_positive": int(tp),
            "operating_threshold": float(threshold),
        }
    )


def choose_threshold(
    y: np.ndarray,
    probability: np.ndarray,
    minimum_recall: float,
    maximum_false_alarm_rate: float | None = None,
) -> tuple[float, dict[str, Any]]:
    all_candidates: list[tuple[float, dict[str, Any]]] = []
    for threshold in np.linspace(0.05, 0.90, 86):
        result = metrics(y, probability, float(threshold))
        if (result["recall"] or 0.0) >= minimum_recall:
            all_candidates.append((float(threshold), result))
    candidates = [
        item for item in all_candidates
        if maximum_false_alarm_rate is None
        or (item[1]["false_alarm_rate"] is not None and item[1]["false_alarm_rate"] <= maximum_false_alarm_rate)
    ]
    if not candidates:
        candidates = all_candidates or [(0.5, metrics(y, probability, 0.5))]
    threshold, result = max(
        candidates,
        key=lambda item: (
            item[1]["f1"] or 0.0,
            -(item[1]["false_alarm_rate"] or 1.0),
            item[1]["precision"] or 0.0,
        ),
    )
    return threshold, result


class ProbabilityCalibrator:
    """Validation-only sigmoid/isotonic calibration with identity fallback."""

    def __init__(self, method: str, model: Any | None = None):
        self.method = method
        self.model = model

    def predict(self, probability: np.ndarray) -> np.ndarray:
        values = np.asarray(probability, dtype=float)
        if self.method == "identity":
            return np.clip(values, 0.0, 1.0)
        if self.method == "sigmoid":
            return self.model.predict_proba(values.reshape(-1, 1))[:, 1]
        return np.clip(self.model.predict(values), 0.0, 1.0)


def fit_calibrator(
    y: np.ndarray,
    probability: np.ndarray,
    reference_prevalence: float | None = None,
    maximum_prevalence_shift: float = 0.25,
) -> tuple[ProbabilityCalibrator, dict[str, Any]]:
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression

    identity = ProbabilityCalibrator("identity")
    candidates: list[ProbabilityCalibrator] = [identity]
    if len(np.unique(y)) == 2:
        sigmoid = LogisticRegression(random_state=RANDOM_SEED, C=1.0)
        sigmoid.fit(np.asarray(probability).reshape(-1, 1), y)
        candidates.append(ProbabilityCalibrator("sigmoid", sigmoid))
        if len(y) >= 100 and min(int(np.sum(y)), int(np.sum(1 - y))) >= 20:
            isotonic = IsotonicRegression(out_of_bounds="clip")
            isotonic.fit(probability, y)
            candidates.append(ProbabilityCalibrator("isotonic", isotonic))
    scored = [(item, brier_score_loss(y, item.predict(probability))) for item in candidates]
    prevalence_shift = (
        abs(float(np.mean(y)) - float(reference_prevalence))
        if reference_prevalence is not None
        else 0.0
    )
    # Do not export a temporary validation base rate when the calibration
    # period is a materially different event regime from training.
    if prevalence_shift > maximum_prevalence_shift:
        selected, score = identity, brier_score_loss(y, identity.predict(probability))
        guard = "IDENTITY_PREVALENCE_SHIFT_GUARD"
    else:
        selected, score = min(scored, key=lambda item: item[1])
        guard = "CANDIDATE_SELECTED_BY_VALIDATION_BRIER"
    return selected, {
        "method": selected.method,
        "validation_brier_before": brier_score_loss(y, identity.predict(probability)),
        "validation_brier_after": score,
        "candidate_brier": {item.method: value for item, value in scored},
        "fit_data": "validation partition only",
        "reference_prevalence": reference_prevalence,
        "validation_prevalence": float(np.mean(y)),
        "absolute_prevalence_shift": prevalence_shift,
        "selection_guard": guard,
    }


@dataclass
class ModelBundle:
    track: str
    version: str
    feature_names: list[str]
    estimator: BaseEstimator
    calibrator: ProbabilityCalibrator
    operating_threshold: float
    risk_thresholds: dict[str, float]
    critical_features: list[str]
    training_medians: dict[str, float]
    training_ranges: dict[str, tuple[float, float]]

    def predict_probability(self, frame: pd.DataFrame) -> np.ndarray:
        raw = self.estimator.predict_proba(frame[self.feature_names])[:, 1]
        return self.calibrator.predict(raw)

    def predict(self, frame: pd.DataFrame) -> list[dict[str, Any]]:
        values = frame[self.feature_names].copy()
        probability = self.predict_probability(values)
        outputs: list[dict[str, Any]] = []
        for row_number, (_, row) in enumerate(values.iterrows()):
            available = float(row[self.critical_features].notna().mean()) if self.critical_features else 1.0
            out_of_range = [
                feature
                for feature in self.feature_names
                if pd.notna(row[feature])
                and (row[feature] < self.training_ranges[feature][0] or row[feature] > self.training_ranges[feature][1])
            ]
            if available < 0.5:
                quality = "INSUFFICIENT"
            elif available < 1.0 or out_of_range:
                quality = "DEGRADED"
            else:
                quality = "GOOD"
            p = float(probability[row_number])
            if p >= self.risk_thresholds["severe"]:
                level = "SEVERE"
            elif p >= self.risk_thresholds["warning"]:
                level = "WARNING"
            elif p >= self.risk_thresholds["watch"]:
                level = "WATCH"
            else:
                level = "NORMAL"
            outputs.append(
                {
                    "model_version": self.version,
                    "risk_type": self.track,
                    "probability": p if quality != "INSUFFICIENT" else None,
                    "risk_level": level if quality != "INSUFFICIENT" else None,
                    "data_quality": quality,
                    "feature_availability": available,
                    "out_of_range_features": out_of_range,
                }
            )
        return outputs


def environment_metadata() -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
        "joblib": joblib.__version__,
        "random_seed": RANDOM_SEED,
    }


def global_and_local_explanations(
    bundle: ModelBundle,
    train: pd.DataFrame,
    test: pd.DataFrame,
    y_test: np.ndarray,
    identifiers: list[str],
    max_rows: int = 2000,
) -> dict[str, Any]:
    sample = test.sample(min(max_rows, len(test)), random_state=RANDOM_SEED) if len(test) else test
    sample_y = y_test[sample.index.to_numpy()] if np.array_equal(test.index, np.arange(len(test))) else test.loc[sample.index, "target"].to_numpy()
    result = permutation_importance(
        bundle.estimator,
        sample[bundle.feature_names],
        sample_y,
        scoring="average_precision",
        n_repeats=3,
        random_state=RANDOM_SEED,
        n_jobs=1,
    )
    global_rows = sorted(
        [
            {"feature": feature, "importance_mean": float(mean), "importance_std": float(std)}
            for feature, mean, std in zip(bundle.feature_names, result.importances_mean, result.importances_std)
        ],
        key=lambda row: row["importance_mean"],
        reverse=True,
    )
    probability = bundle.predict_probability(test)
    selected_rows = np.argsort(-probability)[: min(10, len(test))]
    local_rows = []
    for position in selected_rows:
        observation = test.iloc[[position]].copy()
        base = float(probability[position])
        contributions = []
        for feature in bundle.feature_names:
            changed = observation.copy()
            changed.loc[:, feature] = bundle.training_medians[feature]
            changed_probability = float(bundle.predict_probability(changed)[0])
            contributions.append(
                {
                    "feature": feature,
                    "observed_value": finite_or_none(observation.iloc[0][feature]),
                    "probability_change_if_replaced_by_training_median": base - changed_probability,
                }
            )
        local_rows.append(
            {
                "identifiers": {key: finite_or_none(test.iloc[position][key]) for key in identifiers if key in test},
                "probability": base,
                "top_drivers": sorted(contributions, key=lambda row: abs(row["probability_change_if_replaced_by_training_median"]), reverse=True)[:5],
            }
        )
    return {
        "method": "model-agnostic permutation importance plus median-perturbation local drivers",
        "shap_status": "NOT_APPLICABLE",
        "global_feature_importance": global_rows,
        "local_explanations": local_rows,
    }


def population_stability_index(train: pd.Series, test: pd.Series, bins: int = 10) -> float | None:
    train = pd.to_numeric(train, errors="coerce").dropna()
    test = pd.to_numeric(test, errors="coerce").dropna()
    if train.empty or test.empty or train.nunique() < 2:
        return None
    edges = np.unique(np.quantile(train, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return None
    edges[0], edges[-1] = -np.inf, np.inf
    train_share = pd.cut(train, edges, include_lowest=True).value_counts(normalize=True, sort=False).to_numpy()
    test_share = pd.cut(test, edges, include_lowest=True).value_counts(normalize=True, sort=False).to_numpy()
    train_share = np.clip(train_share, 1e-6, None)
    test_share = np.clip(test_share, 1e-6, None)
    return float(np.sum((test_share - train_share) * np.log(test_share / train_share)))
