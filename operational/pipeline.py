"""P3-07 end-to-end operational intelligence pipeline.

    validate frozen Phase 02 artifacts (checksum)
        -> load the archived Phase 01/02 feature store
        -> select each geography's latest feature row on or before as_of_date
        -> inference through the frozen model bundle
        -> risk classification (frozen thresholds)
        -> geographic enrichment + exposure
        -> driver extraction + reason codes
        -> data-quality / freshness gating
        -> warning-policy evaluation
        -> recommended actions
        -> operational intelligence output (JSON-safe)

Runs against the frozen historical feature archive Phase 01/02 already built.
Live/streaming feature ingestion is out of scope for Phase 03 (see the
Phase 03 report's limitations section); ``as_of_date`` selects "the most
recent information that would have been available on that date" from that
archive, which is what makes the same code path serve both live-style
operational runs and historical replay.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

import pandas as pd

from ml.common import finite_or_none, now, sha256, write_csv, write_json
from operational.geography import UnsupportedGeographyError
from operational.intelligence import PIPELINE_VERSION, build_record, load_verified_bundle

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MODEL_READY = DATA / "model_ready"
OPERATIONAL = DATA / "operational"
TRACKS = ("drought", "flood", "food_security")
GEOGRAPHY_KEY = {"drought": "district_id", "flood": "station_code", "food_security": "region_id"}

STAGES = (
    "FEATURES_READY", "MODEL_LOADED", "INFERENCE_COMPLETE", "EXPOSURE_COMPLETE",
    "WARNING_EVALUATED", "ACTIONS_ATTACHED", "OUTPUT_VALIDATED",
)


def git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def _dataset_meta(track: str) -> dict[str, Any]:
    path = MODEL_READY / track / f"{track}_dataset_v1.1.0.csv.gz"
    return {"dataset_version": "1.1.0", "path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(path)}


def _load_frame(track: str) -> pd.DataFrame:
    frame = pd.read_csv(MODEL_READY / track / f"{track}_dataset_v1.1.0.csv.gz")
    frame["feature_as_of_date"] = pd.to_datetime(frame["feature_as_of_date"])
    return frame


def select_latest_as_of(frame: pd.DataFrame, group_col: str, as_of_date: pd.Timestamp) -> pd.DataFrame:
    """Per geography unit, the most recent feature row on or before as_of_date."""
    eligible = frame[frame.feature_as_of_date <= as_of_date]
    if eligible.empty:
        return eligible
    latest_idx = eligible.groupby(group_col, sort=False)["feature_as_of_date"].idxmax()
    return eligible.loc[latest_idx].reset_index(drop=True)


def run_track(track: str, as_of_date: pd.Timestamp, stage_log: list[str]) -> dict[str, Any]:
    frame = _load_frame(track)
    stage_log.append("FEATURES_READY")
    bundle, model_metadata = load_verified_bundle(track)
    stage_log.append("MODEL_LOADED")
    dataset_meta = _dataset_meta(track)

    rows = select_latest_as_of(frame, GEOGRAPHY_KEY[track], as_of_date)
    records: list[dict[str, Any]] = []
    skipped_unsupported_geography = 0
    for _, row in rows.iterrows():
        try:
            record = build_record(track, row, bundle, model_metadata, dataset_meta)
        except UnsupportedGeographyError:
            skipped_unsupported_geography += 1
            continue
        records.append(record)
    stage_log.append("INFERENCE_COMPLETE")
    stage_log.append("EXPOSURE_COMPLETE")
    stage_log.append("WARNING_EVALUATED")
    stage_log.append("ACTIONS_ATTACHED")

    intelligence_path = OPERATIONAL / "intelligence" / track / f"{as_of_date.date().isoformat()}.json"
    write_json(intelligence_path, records)

    warnings = [record for record in records if record["warning"]["eligible"]]
    warnings_path = OPERATIONAL / "warnings" / track / f"{as_of_date.date().isoformat()}.json"
    write_json(warnings_path, warnings)

    exposure_rows = pd.DataFrame([
        {
            "risk_type": record["risk_type"], "geography_type": record["geography"]["type"],
            "geography_id": record["geography"]["id"], "as_of_date": record["as_of_date"],
            "risk_probability": record["prediction"]["probability"], "risk_level": record["prediction"]["risk_level"],
            "population_context": record["exposure"]["population_context"],
            "population_potentially_exposed": record["exposure"]["population_potentially_exposed"],
            "exposure_method": record["exposure"]["exposure_method"],
            "source_version": record["lineage"]["dataset_version"], "model_version": record["model"]["version"],
            "quality_status": record["data_quality"]["overall_status"],
        }
        for record in records
    ])
    exposure_path = OPERATIONAL / "exposure" / track / f"{as_of_date.date().isoformat()}.csv"
    write_csv(exposure_path, exposure_rows)
    stage_log.append("OUTPUT_VALIDATED")

    counts = {"NORMAL": 0, "WATCH": 0, "WARNING": 0, "SEVERE": 0, "UNKNOWN": 0}
    for record in records:
        counts[record["prediction"]["risk_level"]] = counts.get(record["prediction"]["risk_level"], 0) + 1

    return {
        "track": track, "as_of_date": as_of_date.date().isoformat(), "rows_evaluated": len(records),
        "skipped_unsupported_geography": skipped_unsupported_geography,
        "risk_level_counts": counts,
        "warning_eligible_count": len(warnings),
        "population_context_total": float(exposure_rows.population_context.sum()) if len(exposure_rows) else 0.0,
        "population_potentially_exposed_total": (
            float(exposure_rows.population_potentially_exposed.sum())
            if len(exposure_rows) and exposure_rows.population_potentially_exposed.notna().any()
            else None
        ),
        "intelligence_path": str(intelligence_path.relative_to(ROOT)).replace("\\", "/"),
        "warnings_path": str(warnings_path.relative_to(ROOT)).replace("\\", "/"),
        "exposure_path": str(exposure_path.relative_to(ROOT)).replace("\\", "/"),
        "model_id": model_metadata["model_id"], "model_version": model_metadata["model_version"],
        "dataset_checksum": dataset_meta["sha256"],
    }


def run(as_of_date: str | None = None, tracks: tuple[str, ...] = TRACKS) -> dict[str, Any]:
    started = time.perf_counter()
    stage_log: list[str] = []
    resolved_dates: dict[str, str] = {}
    track_results = {}
    for track in tracks:
        frame = _load_frame(track)
        effective_as_of = pd.Timestamp(as_of_date) if as_of_date else frame.feature_as_of_date.max()
        resolved_dates[track] = effective_as_of.date().isoformat()
        track_results[track] = run_track(track, effective_as_of, stage_log)

    summary = {
        "generated_at": now(),
        "pipeline_version": PIPELINE_VERSION,
        "git_commit": git_commit(),
        "as_of_date_requested": as_of_date,
        "as_of_date_resolved": resolved_dates,
        "tracks": track_results,
        "stages_completed": sorted(set(stage_log)),
        "run_seconds": time.perf_counter() - started,
    }

    national_summary = {
        "as_of_date": resolved_dates,
        "pipeline_version": PIPELINE_VERSION,
        "generated_at": summary["generated_at"],
        "note": "Unit counts only. No national probability is produced by averaging heterogeneous per-unit model outputs.",
        **{
            track: {
                "risk_level_counts": track_results[track]["risk_level_counts"],
                "warning_eligible_units": track_results[track]["warning_eligible_count"],
                "units_evaluated": track_results[track]["rows_evaluated"],
                "population_context_total": track_results[track]["population_context_total"],
            }
            for track in tracks
        },
    }
    summary_key = "-".join(sorted(set(resolved_dates.values()))) if len(set(resolved_dates.values())) == 1 else "mixed"
    write_json(OPERATIONAL / "summary" / f"national_summary_{summary_key}.json", finite_or_none(national_summary))
    write_json(OPERATIONAL / "summary" / "latest_run_summary.json", finite_or_none(summary))
    return finite_or_none(summary)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run the Phase 03 operational intelligence pipeline")
    parser.add_argument("--as-of-date", default=None, help="ISO date; defaults to the latest available date per track")
    parser.add_argument("--tracks", nargs="*", default=list(TRACKS))
    args = parser.parse_args()
    summary = run(as_of_date=args.as_of_date, tracks=tuple(args.tracks))
    print(json.dumps({
        "as_of_date_resolved": summary["as_of_date_resolved"],
        "tracks": {track: {"rows_evaluated": value["rows_evaluated"], "warning_eligible_count": value["warning_eligible_count"]} for track, value in summary["tracks"].items()},
        "run_seconds": summary["run_seconds"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
