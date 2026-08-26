"""P3-04 operational historical replay.

Re-runs the FULL operational chain (geography -> exposure -> drivers ->
quality/freshness -> warning -> actions), not just the raw Phase 02 model
probability, over every row of the frozen, untouched Phase 02 final-test
partition for each track. The partition is the exact same one Phase 02 froze
(``ml.pipeline.partition``, keyed on ``target_period_start``) -- Phase 03
does not redefine it. No row is cherry-picked: the selection is simply
"every row in the already-frozen test partition". Frozen models are loaded
read-only; nothing is retrained.

Two outcome classifications are reported side by side, deliberately never
collapsed into one number:

* ``outcome_at_warning_threshold`` -- detected iff risk_level is WARNING or
  SEVERE (probability >= the frozen Phase 02 operating threshold). This is
  the same decision boundary behind Phase 02's validated recall/precision,
  so it should reproduce those model-card numbers.
* ``outcome_at_watch_threshold`` -- detected iff risk_level is WATCH or
  above (the broader "warning_eligible" monitoring net). This is
  intentionally more sensitive and must not be compared to Phase 02's
  model-card metrics as if it were the same measurement.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

from ml.common import finite_or_none, now, write_csv, write_json
from ml.pipeline import SPLITS, partition as phase02_partition
from operational.geography import UnsupportedGeographyError
from operational.intelligence import build_record, load_verified_bundle
from operational.pipeline import _dataset_meta, _load_frame

ROOT = Path(__file__).resolve().parents[1]
OPERATIONAL = ROOT / "data" / "operational"

RISK_AT_OR_ABOVE = {
    "warning_threshold": {"WARNING", "SEVERE"},
    "watch_threshold": {"WATCH", "WARNING", "SEVERE"},
}


def _outcome(row: pd.Series, detected: bool) -> str:
    target = row.get("target")
    if pd.isna(target):
        return "UNKNOWN_TARGET"
    actual = bool(int(target))
    if detected and actual:
        return "TRUE_POSITIVE"
    if detected and not actual:
        return "FALSE_POSITIVE"
    if not detected and actual:
        return "FALSE_NEGATIVE"
    return "TRUE_NEGATIVE"


def _confusion(frame: pd.DataFrame, outcome_col: str) -> dict[str, Any]:
    counts = frame[outcome_col].value_counts().to_dict() if len(frame) else {}
    tp, fp, fn, tn = (counts.get(k, 0) for k in ("TRUE_POSITIVE", "FALSE_POSITIVE", "FALSE_NEGATIVE", "TRUE_NEGATIVE"))
    return {
        "counts": counts,
        "recall": tp / (tp + fn) if (tp + fn) else None,
        "precision": tp / (tp + fp) if (tp + fp) else None,
        "false_alarm_rate": fp / (fp + tn) if (fp + tn) else None,
    }


def replay_track(track: str) -> tuple[dict[str, Any], pd.DataFrame]:
    started = time.perf_counter()
    frame = _load_frame(track)
    test = phase02_partition(frame, track)["test"]
    bundle, model_metadata = load_verified_bundle(track)
    dataset_meta = _dataset_meta(track)

    rows = []
    skipped_unsupported_geography = 0
    for _, row in test.iterrows():
        try:
            record = build_record(track, row, bundle, model_metadata, dataset_meta, include_drivers=False)
        except UnsupportedGeographyError:
            skipped_unsupported_geography += 1
            continue
        risk_level = record["prediction"]["risk_level"]
        detected_warning = risk_level in RISK_AT_OR_ABOVE["warning_threshold"]
        detected_watch = risk_level in RISK_AT_OR_ABOVE["watch_threshold"]
        rows.append({
            "intelligence_id": record["intelligence_id"],
            "geography_type": record["geography"]["type"], "geography_id": record["geography"]["id"],
            "geography_name": record["geography"]["name"],
            "as_of_date": record["as_of_date"], "target_period_start": row.get("target_period_start"),
            "probability": record["prediction"]["probability"], "risk_level": risk_level,
            "warning_eligible": record["warning"]["eligible"], "warning_status": record["warning"]["status"],
            "population_context": record["exposure"]["population_context"],
            "population_potentially_exposed": record["exposure"]["population_potentially_exposed"],
            "observed_target": None if pd.isna(row.get("target")) else int(row.get("target")),
            "outcome_at_warning_threshold": _outcome(row, detected_warning),
            "outcome_at_watch_threshold": _outcome(row, detected_watch),
            "lead_time_days": row.get("target_first_crossing_lead_days") if track == "flood" else None,
            "recommended_action_count": len(record["recommended_actions"]),
            "data_quality_status": record["data_quality"]["overall_status"],
        })

    replay_frame = pd.DataFrame(rows)
    replay_path = OPERATIONAL / "replay" / f"{track}_operational_replay.csv.gz"
    write_csv(replay_path, replay_frame)

    at_warning = _confusion(replay_frame, "outcome_at_warning_threshold")
    at_watch = _confusion(replay_frame, "outcome_at_watch_threshold")

    station_breakdown = None
    if track == "flood" and len(replay_frame):
        station_breakdown = {
            station: _confusion(group, "outcome_at_warning_threshold")
            for station, group in replay_frame.groupby("geography_id")
        }

    true_positive_mask = replay_frame.outcome_at_warning_threshold == "TRUE_POSITIVE"
    summary = {
        "track": track,
        "generated_at": now(),
        "test_period": SPLITS[track]["test"],
        "rows_replayed": len(replay_frame),
        "skipped_unsupported_geography": skipped_unsupported_geography,
        "outcome_at_warning_threshold": at_warning,
        "outcome_at_watch_threshold": at_watch,
        "mean_detected_lead_time_days": (
            float(replay_frame.loc[true_positive_mask, "lead_time_days"].mean())
            if track == "flood" and true_positive_mask.any()
            else None
        ),
        "station_breakdown_at_warning_threshold": station_breakdown,
        "replay_path": str(replay_path.relative_to(ROOT)).replace("\\", "/"),
        "replay_seconds": time.perf_counter() - started,
        "model_version": model_metadata["model_version"],
        "selection_methodology": "every row in the frozen, untouched Phase 02 final-test partition (ml.pipeline.partition); no cherry-picking",
    }
    write_json(OPERATIONAL / "replay" / f"{track}_replay_summary.json", finite_or_none(summary))
    return finite_or_none(summary), replay_frame


def illustrative_cases(replay_frame: pd.DataFrame, n: int = 3) -> dict[str, list[dict[str, Any]]]:
    """A handful of concrete examples (at the warning threshold) for the narrative report."""
    def top(outcome: str, ascending: bool = False) -> list[dict[str, Any]]:
        subset = replay_frame[replay_frame.outcome_at_warning_threshold == outcome]
        if subset.empty:
            return []
        subset = subset.sort_values("probability", ascending=ascending).head(n)
        return subset.to_dict("records")

    return {
        "highest_confidence_true_positives": top("TRUE_POSITIVE", ascending=False),
        "highest_confidence_false_positives": top("FALSE_POSITIVE", ascending=False),
        "lowest_confidence_false_negatives": top("FALSE_NEGATIVE", ascending=True),
    }


def run_all() -> dict[str, Any]:
    results = {}
    for track in ("drought", "flood", "food_security"):
        summary, replay_frame = replay_track(track)
        results[track] = summary
        write_json(OPERATIONAL / "replay" / f"{track}_illustrative_cases.json", finite_or_none(illustrative_cases(replay_frame)))
    return results


if __name__ == "__main__":
    print(json.dumps(run_all(), indent=2, default=str))
