"""Phase 02 readiness validator.

Reads the already-frozen Phase 02 artifacts produced by ``python -m ml.pipeline run``
(no retraining, no re-tuning) and:

1. Computes the flood per-station backtest breakdown from the stored rolling
   backtest predictions (SH001, SH002, SH004, JB001, JB009 reported separately,
   never averaged away).
2. Evaluates each track's final test-period metrics against the acceptance
   criteria that were predeclared in ``ml/config/acceptance.json`` *before*
   the final test partition was ever inspected, and classifies each track as
   VALIDATED / CONDITIONALLY_VALIDATED / REJECTED.
3. Confirms every Phase 02 acceptance-gate checklist item (targets, datasets,
   leakage, baselines, advanced models, backtest, calibration, explainability,
   artifacts, documentation, testing).
4. Writes ``data/metadata/phase02_completion_report.json``.

This script never fits or refits a model and never changes a metric. It only
reads existing frozen artifacts and reports on them honestly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ml.common import now, write_json  # noqa: E402

ML = ROOT / "ml"
DATA = ROOT / "data"
REPORTS = ML / "reports"
ARTIFACTS = ML / "artifacts"
METADATA = DATA / "metadata"
DOCS = ROOT / "docs"

STATIONS = ["SH001", "SH002", "SH004", "JB001", "JB009"]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def flood_station_breakdown() -> dict[str, Any]:
    """Per-station rolling-backtest metrics; no station is averaged away."""
    path = ARTIFACTS / "flood" / "rolling_backtest_predictions.csv.gz"
    frame = pd.read_csv(path)
    stations: dict[str, Any] = {}
    for station in STATIONS:
        subset = frame[frame.station_code == station]
        if subset.empty:
            stations[station] = {"rows": 0, "status": "NO_ROWS"}
            continue
        y = subset.target.to_numpy(dtype=int)
        pred = subset.prediction.to_numpy(dtype=int)
        tn = int(((y == 0) & (pred == 0)).sum())
        fp = int(((y == 0) & (pred == 1)).sum())
        fn = int(((y == 1) & (pred == 0)).sum())
        tp = int(((y == 1) & (pred == 1)).sum())
        recall = tp / (tp + fn) if (tp + fn) else None
        precision = tp / (tp + fp) if (tp + fp) else None
        false_alarm_rate = fp / (fp + tn) if (fp + tn) else None
        miss_rate = fn / (fn + tp) if (fn + tp) else None
        detected = subset[(subset.target == 1) & (subset.prediction == 1)]
        lead_time = (
            float(detected.target_first_crossing_lead_days.mean())
            if "target_first_crossing_lead_days" in detected and not detected.empty
            else None
        )
        stations[station] = {
            "rows": int(len(subset)),
            "positives": int(y.sum()),
            "negatives": int((1 - y).sum()),
            "true_negative": tn,
            "false_positive": fp,
            "false_negative": fn,
            "true_positive": tp,
            "recall": recall,
            "precision": precision,
            "false_alarm_rate": false_alarm_rate,
            "miss_rate": miss_rate,
            "mean_detected_lead_time_days": lead_time,
            "status": "EVALUATED" if (tp + fn) > 0 else "NO_POSITIVE_EVENTS_IN_BACKTEST",
        }
    write_json(ARTIFACTS / "flood" / "station_backtest.json", {
        "generated_at": now(),
        "source": "ml/artifacts/flood/rolling_backtest_predictions.csv.gz",
        "note": "Computed from the frozen rolling backtest; no retraining performed.",
        "stations": stations,
    })
    return stations


def evaluate_track_acceptance(
    track: str,
    run_summary: dict[str, Any],
    acceptance: dict[str, Any],
    station_breakdown: dict[str, Any] | None,
) -> dict[str, Any]:
    common = acceptance["common"]
    rules = acceptance[track]
    model = run_summary["models"][track]
    dataset = run_summary["dataset_build"][track]
    backtest = run_summary["backtesting"][track]
    final = model["final_test_metrics"]
    partitions = model["partitions"]
    calibration = model["calibration"]

    train_pos = partitions["train"]["positive"]
    train_neg = partitions["train"]["negative"]
    val_pos = partitions["validation"]["positive"]
    val_neg = partitions["validation"]["negative"]
    pr_auc = final.get("pr_auc") or 0.0
    prevalence = final.get("prevalence") or 1e-9
    false_alarm_rate = final.get("false_alarm_rate")
    brier_degradation = calibration["test_brier_after"] - calibration["test_brier_before"]

    checks = {
        "minimum_rows": dataset["rows"] >= rules["minimum_rows"],
        "minimum_positive_train_validation": (train_pos + val_pos) >= common["minimum_positive_train_validation"],
        "minimum_negative_train_validation": (train_neg + val_neg) >= common["minimum_negative_train_validation"],
        "minimum_positive_test": partitions["test"]["positive"] >= common["minimum_positive_test"],
        "minimum_negative_test": partitions["test"]["negative"] >= common["minimum_negative_test"],
        "minimum_backtest_folds": backtest["fold_count"] >= common["minimum_backtest_folds"],
        "minimum_test_pr_auc_relative_to_prevalence": (pr_auc / prevalence) >= rules["minimum_test_pr_auc_relative_to_prevalence"],
        "minimum_test_recall": (final.get("recall") or 0.0) >= rules["minimum_test_recall"],
        "maximum_false_alarm_rate": (false_alarm_rate if false_alarm_rate is not None else 1.0) <= rules["maximum_false_alarm_rate"],
        "calibration_no_material_degradation": brier_degradation <= common["maximum_calibrated_brier_degradation"],
        "serialization_round_trip": bool(model["artifact"]["serialization_round_trip_passed"]) if common["require_serialization_round_trip"] else True,
        "explainability_available": bool(model["explainability"]["available"]) if common["require_global_and_local_explanations"] else True,
        "no_leakage": run_summary["leakage"]["tracks"][track]["status"] == "PASS" if common["require_no_leakage"] else True,
    }
    if rules.get("require_station_breakdown"):
        checks["station_breakdown_reported"] = bool(station_breakdown) and all(
            station_breakdown.get(station, {}).get("rows", 0) > 0 for station in STATIONS
        )

    all_pass = all(checks.values())
    core_predictive_and_safe = (
        checks["minimum_test_pr_auc_relative_to_prevalence"]
        and checks["minimum_test_recall"]
        and checks["maximum_false_alarm_rate"]
        and checks["no_leakage"]
        and checks["serialization_round_trip"]
    )
    if all_pass:
        status = "VALIDATED"
    elif core_predictive_and_safe:
        status = "CONDITIONALLY_VALIDATED"
    else:
        status = "REJECTED"

    failing = [name for name, passed in checks.items() if not passed]
    return {
        "track": track,
        "selected_model": model["selected_model"],
        "status": status,
        "checks": checks,
        "failing_checks": failing,
        "measured": {
            "test_rows": final["rows"],
            "test_prevalence": final.get("prevalence"),
            "test_recall": final.get("recall"),
            "test_precision": final.get("precision"),
            "test_pr_auc": final.get("pr_auc"),
            "test_pr_auc_relative_to_prevalence": pr_auc / prevalence,
            "test_roc_auc": final.get("roc_auc"),
            "test_false_alarm_rate": false_alarm_rate,
            "test_miss_rate": final.get("miss_rate"),
            "test_brier": calibration["test_brier_after"],
            "backtest_folds": backtest["fold_count"],
            "mean_detected_lead_time_days": backtest.get("mean_detected_lead_time_days"),
        },
    }


def checklist(run_summary: dict[str, Any], leakage: dict[str, Any], test_report: dict[str, Any], acceptance_by_track: dict[str, Any]) -> dict[str, Any]:
    def exists(*parts: str) -> bool:
        return (ROOT / Path(*parts)).exists()

    targets = {
        "drought_target_defined": exists("docs", "phase-02-target-definitions.md") and exists("ml", "config", "targets.json"),
        "flood_target_defined": exists("ml", "config", "targets.json"),
        "food_security_target_defined": exists("ml", "config", "targets.json"),
    }
    datasets = {
        f"{track}_model_dataset_valid": exists("data", "model_ready", track, f"{track}_dataset_v1.1.0.csv.gz")
        for track in ("drought", "flood", "food_security")
    }
    leakage_checks = {
        "no_temporal_leakage": leakage["status"] == "PASS",
        "no_target_leakage": all(v["status"] == "PASS" for v in leakage["tracks"].values()),
        "split_integrity_verified": all(v["checks"].get("split_time_order", False) for v in leakage["tracks"].values()),
    }
    baselines = {
        f"{track}_baseline_evaluated": "rule" in run_summary["models"][track]["baseline"]
        for track in ("drought", "flood", "food_security")
    }
    advanced = {
        "candidate_models_evaluated": all(len(run_summary["models"][track]["candidates"]) >= 1 for track in ("drought", "flood", "food_security")),
        "final_selection_justified": all(bool(run_summary["models"][track]["selection_reason"]) for track in ("drought", "flood", "food_security")),
    }
    backtest = {
        f"{track}_backtested": run_summary["backtesting"][track]["fold_count"] >= 3
        for track in ("drought", "flood", "food_security")
    }
    calibration = {
        "final_probabilistic_models_calibrated_or_deemed_unnecessary": all(
            run_summary["models"][track]["calibration"]["method"] in ("identity", "sigmoid", "isotonic")
            for track in ("drought", "flood", "food_security")
        ),
    }
    explainability = {
        "global_explanations_available": all(run_summary["models"][track]["explainability"]["available"] for track in ("drought", "flood", "food_security")),
        "local_explanations_supported": all(
            "local_explanations" in load_json(ARTIFACTS / track / "explainability.json")
            for track in ("drought", "flood", "food_security")
        ),
    }
    artifacts = {
        "model_artifacts_exist": all(exists("ml", "artifacts", track, Path(run_summary["models"][track]["artifact"]["artifact_path"]).name) for track in ("drought", "flood", "food_security")),
        "feature_schemas_exist": all(exists("data", "model_ready", track, "feature_schema_v1.1.0.json") for track in ("drought", "flood", "food_security")),
        "metadata_exists": all(exists("ml", "artifacts", track, "model_metadata.json") for track in ("drought", "flood", "food_security")),
        "checksums_exist": all(bool(run_summary["models"][track]["artifact"]["artifact_checksum_sha256"]) for track in ("drought", "flood", "food_security")),
    }
    documentation = {
        "model_cards_exist": all(
            exists("docs", "models", name) for name in ("drought-model-card.md", "flood-model-card.md", "food-security-model-card.md")
        ),
        "phase02_report_exists": exists("docs", "phase-02-ai-modeling-report.md"),
        "reproduction_instructions_exist": exists("docs", "phase-02-ai-modeling-report.md"),
    }
    testing = {
        "automated_tests_pass": test_report.get("status") == "PASS",
        "leakage_tests_pass": leakage["status"] == "PASS",
        "serialization_tests_pass": all(run_summary["models"][track]["artifact"]["serialization_round_trip_passed"] for track in ("drought", "flood", "food_security")),
    }
    acceptance_gate = {
        f"{track}_acceptance": acceptance_by_track[track]["status"] for track in ("drought", "flood", "food_security")
    }
    return {
        "targets": targets,
        "datasets": datasets,
        "leakage": leakage_checks,
        "baselines": baselines,
        "advanced_models": advanced,
        "backtest": backtest,
        "calibration": calibration,
        "explainability": explainability,
        "artifacts": artifacts,
        "documentation": documentation,
        "testing": testing,
        "acceptance_gate": acceptance_gate,
    }


def main() -> int:
    run_summary = load_json(REPORTS / "phase02_run_summary.json")
    acceptance = load_json(ML / "config" / "acceptance.json")
    leakage = load_json(METADATA / "phase02_leakage_report.json")
    test_report_path = METADATA / "phase02_test_report.json"
    test_report = load_json(test_report_path) if test_report_path.exists() else {"status": "MISSING"}
    target_summary = load_json(METADATA / "phase02_target_summary.json")

    station_breakdown = flood_station_breakdown()

    acceptance_results = {
        track: evaluate_track_acceptance(track, run_summary, acceptance, station_breakdown if track == "flood" else None)
        for track in ("drought", "flood", "food_security")
    }

    checks = checklist(run_summary, leakage, test_report, acceptance_results)
    checklist_all_pass = all(
        all(section.values()) if isinstance(section, dict) else bool(section)
        for key, section in checks.items()
        if key != "acceptance_gate"
    )
    tracks_validated = all(result["status"] == "VALIDATED" for result in acceptance_results.values())

    phase02_status = "COMPLETE" if (checklist_all_pass and tracks_validated) else "NOT COMPLETE"

    completion_report = {
        "phase": "02",
        "generated_at": now(),
        "phase02_version": run_summary.get("phase02_version"),
        "git_commit": run_summary.get("git_commit"),
        "status": phase02_status,
        "models": {
            track: {
                "acceptance_status": acceptance_results[track]["status"],
                "selected_model": acceptance_results[track]["selected_model"],
                "measured_metrics": acceptance_results[track]["measured"],
                "failing_checks": acceptance_results[track]["failing_checks"],
                "artifact_path": run_summary["models"][track]["artifact"]["artifact_path"],
                "artifact_checksum_sha256": run_summary["models"][track]["artifact"]["artifact_checksum_sha256"],
                "operating_threshold": run_summary["models"][track]["operating_threshold"],
                "risk_thresholds": run_summary["models"][track]["risk_thresholds"],
                "calibration_method": run_summary["models"][track]["calibration"]["method"],
            }
            for track in ("drought", "flood", "food_security")
        },
        "flood_station_backtest": station_breakdown,
        "backtesting": {
            track: {
                "fold_count": run_summary["backtesting"][track]["fold_count"],
                "overall_metrics": run_summary["backtesting"][track]["overall_metrics"],
                "mean_detected_lead_time_days": run_summary["backtesting"][track].get("mean_detected_lead_time_days"),
            }
            for track in ("drought", "flood", "food_security")
        },
        "calibration": {
            track: run_summary["models"][track]["calibration"] for track in ("drought", "flood", "food_security")
        },
        "explainability": {
            track: {
                "available": run_summary["models"][track]["explainability"]["available"],
                "method": run_summary["models"][track]["explainability"]["method"],
                "shap_status": run_summary["models"][track]["explainability"]["shap_status"],
            }
            for track in ("drought", "flood", "food_security")
        },
        "tests": test_report,
        "target_summary_reference": "data/metadata/phase02_target_summary.json",
        "target_positive_rates": {
            track: target_summary["tracks"][track]["positive_rate"] for track in ("drought", "flood", "food_security")
        },
        "checklist": checks,
        "blockers": [] if phase02_status == "COMPLETE" else sorted(
            {
                f"{track}: {check}"
                for track, result in acceptance_results.items()
                for check in result["failing_checks"]
            }
            | {
                f"checklist.{section}.{item}"
                for section, values in checks.items()
                if isinstance(values, dict) and section != "acceptance_gate"
                for item, passed in values.items()
                if not passed
            }
        ),
    }
    write_json(METADATA / "phase02_completion_report.json", completion_report)

    print(json.dumps({
        "phase02_status": phase02_status,
        "tracks": {track: result["status"] for track, result in acceptance_results.items()},
        "checklist_all_pass": checklist_all_pass,
    }, indent=2))
    return 0 if phase02_status == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
