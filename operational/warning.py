"""P3-05 warning logic: deterministic quality gating, freshness, and warning status.

Risk level and warning workflow status are kept explicitly separate (Rule 25):
a WARNING-level probability with insufficient or stale critical data does not
become a published warning candidate -- it is suppressed with a structured,
traceable reason, and the underlying model output is preserved separately.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FRESHNESS_POLICY = json.loads((ROOT / "operational" / "config" / "freshness_policy.json").read_text(encoding="utf-8"))

NORMAL = "NORMAL"


def freshness_assessment(track: str, row: pd.Series, as_of_date: pd.Timestamp) -> dict[str, Any]:
    policy = FRESHNESS_POLICY[track]
    gaps: dict[str, Any] = {}
    stale_critical: list[str] = []
    stale_noncritical: list[str] = []
    for column, rule in policy.items():
        if column not in row or pd.isna(row[column]):
            gaps[column] = {"gap_days": None, "status": "MISSING", "max_gap_days": rule["max_gap_days"]}
            (stale_critical if rule["critical"] else stale_noncritical).append(column)
            continue
        timestamp = pd.to_datetime(row[column])
        gap_days = (as_of_date - timestamp).days
        stale = gap_days > rule["max_gap_days"]
        gaps[column] = {"gap_days": int(gap_days), "status": "STALE" if stale else "CURRENT", "max_gap_days": rule["max_gap_days"]}
        if stale:
            (stale_critical if rule["critical"] else stale_noncritical).append(column)
    if stale_critical:
        status = "STALE_CRITICAL"
    elif stale_noncritical:
        status = "DEGRADED"
    else:
        status = "GOOD"
    return {
        "status": status,
        "policy_version": FRESHNESS_POLICY["version"],
        "stale_critical_features": stale_critical,
        "stale_noncritical_features": stale_noncritical,
        "detail": gaps,
    }


def combined_data_quality(model_quality: str, freshness_status: str) -> str:
    """Worse-of(model input quality, freshness) -- never optimistic."""
    if model_quality == "INSUFFICIENT" or freshness_status == "STALE_CRITICAL":
        return "INSUFFICIENT"
    if model_quality == "DEGRADED" or freshness_status == "DEGRADED":
        return "DEGRADED"
    return "GOOD"


def warning_decision(risk_level: str, model_quality: str, freshness_status: str, overall_quality: str) -> dict[str, Any]:
    if risk_level == NORMAL:
        return {
            "eligible": False,
            "status": "NO_WARNING_RISK_NORMAL",
            "suppression_reason": None,
        }
    if overall_quality == "INSUFFICIENT":
        if freshness_status == "STALE_CRITICAL":
            reason = "critical source data is stale beyond its documented freshness policy"
            suppression = "SUPPRESSED_STALE_DATA"
        else:
            reason = "critical model features are unavailable or out of the trained guardrail range"
            suppression = "SUPPRESSED_DATA_QUALITY"
        return {
            "eligible": False,
            "status": suppression,
            "suppression_reason": reason,
        }
    return {
        "eligible": True,
        "status": "CANDIDATE",
        "suppression_reason": None,
    }
