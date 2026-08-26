"""Programmatic Phase 01 acceptance and Phase 02 data-readiness gate."""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "metadata"
OUTPUT = METADATA / "phase01_readiness.json"


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            return list(csv.DictReader(stream))
    except OSError:
        return []


def check(name: str, passed: bool, evidence: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "evidence": evidence}


def main() -> int:
    rainfall = read_json(METADATA / "chirps_historical_validation.json")
    vegetation = read_json(METADATA / "mod13q1_historical_validation.json")
    power = read_json(METADATA / "nasa_power_history_validation.json")
    rivers = read_json(METADATA / "river_station_metadata_validation.json")
    boundaries = read_json(METADATA / "boundary_provenance_validation.json")
    ipc = read_json(ROOT / "processed" / "food_security" / "ipc_geographic_mapping.json")
    base_validation = read_json(METADATA / "phase01_validation_report.json")
    source_audit = read_json(METADATA / "validation_report.json")
    history_manifest = read_csv(METADATA / "historical_archive_manifest.csv")
    crosswalk = read_csv(METADATA / "geographic_crosswalk.csv")
    banadir = read_csv(ROOT / "processed" / "market_prices" / "wfp_banadir_geographic_resolution.csv")

    ipc_checks = ipc.get("summary", {}).get("validation_checks", {})
    river_checks = rivers.get("station_checks", [])
    rainfall_ready = (
        rainfall.get("status") == "COMPLETE"
        and rainfall.get("start", "9999") <= "2015-01-01"
        and rainfall.get("end", "0000") >= "2025-12-31"
        and int(rainfall.get("actual_days", 0)) >= 4018
        and int(rainfall.get("districts", 0)) == 91
        and not rainfall.get("missing_dates")
        and int(rainfall.get("missing_district_day_rows", 1)) == 0
    )
    vegetation_ready = (
        vegetation.get("status") == "COMPLETE"
        and vegetation.get("start", "9999") <= "2015-01-01"
        and vegetation.get("end", "0000") >= "2025-12-31"
        and int(vegetation.get("periods", 0)) >= 240
        and int(vegetation.get("districts", 0)) == 91
        # Dense, tiny Banadir polygons are not required to fabricate a
        # vegetation observation at the approximately 1 km summary grid.
        # Preserve strict-QA nulls while requiring strong coverage elsewhere
        # and bounding the archive-wide missingness.
        and float(vegetation.get("missing_non_banadir_district_period_fraction", 1.0)) <= 0.10
        and float(vegetation.get("missing_district_period_fraction", 1.0)) <= 0.20
        and "pixel_reliability=0" in str(vegetation.get("qa_rule", ""))
    )
    power_ready = (
        power.get("status") == "COMPLETE"
        and power.get("period", {}).get("start") == "20000101"
        and power.get("period", {}).get("end") == "20251231"
        and int(power.get("geography", {}).get("district_count", 0)) == 91
        and not any(power.get("missing_values", {}).values())
    )
    river_ready = (
        rivers.get("passed") is True
        and int(rivers.get("station_csv_count", 0)) == 5
        and int(rivers.get("observation_rows", 0)) == 87848
        and all(row.get("threshold_order_valid") for row in river_checks)
    )
    boundary_ready = boundaries.get("passed") is True
    ipc_ready = bool(ipc_checks) and all(ipc_checks.values())
    banadir_ready = len(banadir) == 10 and all(row.get("canonical_district_id") for row in banadir)
    market_ready = base_validation.get("market_prices", {}).get("status") in {"PASS", "REVIEW"}
    population_ready = base_validation.get("population", {}).get("status") == "PASS"
    registry_ready = (METADATA / "source_registry.csv").exists() and (METADATA / "source_registry.json").exists()
    matrices_ready = all(
        (METADATA / name).exists()
        for name in ("data_availability_matrix.csv", "temporal_coverage_matrix.csv", "geographic_crosswalk.csv")
    )
    manifests_ready = (
        any("CHIRPS" in row.get("dataset", "") and row.get("status") == "COMPLETE" for row in history_manifest)
        and any("MOD13Q1" in row.get("dataset", "") and row.get("status") == "COMPLETE" for row in history_manifest)
        and (METADATA / "nasa_power_history_manifest.json").exists()
    )
    crosswalk_ready = len(crosswalk) >= 218
    temporal_doc_ready = (ROOT.parent / "docs" / "temporal-alignment-strategy.md").exists()
    source_integrity_ready = not any(
        source_audit.get(field, [])
        for field in ("zero_byte_files", "suspected_partial_downloads", "unreadable_files")
    )
    duplicate_ready = not source_audit.get("exact_duplicate_groups", [])
    overlap_ready = (METADATA / "temporal_overlap_report.json").exists()

    common = {
        "boundaries": boundary_ready,
        "rainfall": rainfall_ready,
        "temperature_and_antecedent_wetness": power_ready,
    }
    models = {
        "DROUGHT": {
            "status": "READY" if all(common.values()) and vegetation_ready else "BLOCKED",
            "window": {"start": "2015-01-01", "end": "2025-12-31", "calendar": "dekad"},
            "requirements": {**common, "vegetation": vegetation_ready},
        },
        "FLOOD": {
            "status": "READY" if all(common.values()) and river_ready else "BLOCKED",
            "window": {"start": "2015-01-01", "end": "2025-12-31", "calendar": "daily plus dekad"},
            "requirements": {**common, "river_observations_and_metadata": river_ready},
        },
        "FOOD_SECURITY": {
            "status": (
                "READY"
                if all(common.values()) and vegetation_ready and ipc_ready and market_ready and banadir_ready
                else "BLOCKED"
            ),
            "window": {"start": "2017-01-01", "end": "2025-12-31", "calendar": "dekad predictors; IPC assessment target"},
            "requirements": {
                **common,
                "vegetation": vegetation_ready,
                "ipc_geographic_interpretation": ipc_ready,
                "market_prices": market_ready,
                "banadir_quarantine_and_point_mapping": banadir_ready,
            },
        },
    }
    acceptance = [
        check("boundaries_structural_and_metadata", boundary_ready, boundaries),
        check("historical_chirps", rainfall_ready, rainfall),
        check("historical_mod13q1", vegetation_ready, vegetation),
        check("historical_wetness_equivalent", power_ready, power),
        check("historical_temperature", power_ready, power),
        check("river_coordinates_thresholds_observations", river_ready, rivers),
        check("ipc_geographic_interpretation", ipc_ready, ipc.get("summary", {})),
        check("market_banadir_safely_isolated", banadir_ready, {"rows": len(banadir)}),
        check("population_documented", population_ready, base_validation.get("population", {})),
        check("registries", registry_ready, "data/metadata/source_registry.csv|json"),
        check("matrices", matrices_ready, "availability, temporal coverage, geographic crosswalk"),
        check("historical_manifests", manifests_ready, {"rows": len(history_manifest)}),
        check("crosswalk", crosswalk_ready, {"rows": len(crosswalk)}),
        check("temporal_alignment_strategy", temporal_doc_ready, "docs/temporal-alignment-strategy.md"),
        check(
            "zero_corrupted_or_partial_source_files",
            source_integrity_ready,
            {
                "zero_byte": len(source_audit.get("zero_byte_files", [])),
                "partial": len(source_audit.get("suspected_partial_downloads", [])),
                "unreadable": len(source_audit.get("unreadable_files", [])),
            },
        ),
        check(
            "zero_unexplained_duplicate_downloads",
            duplicate_ready,
            {"exact_duplicate_groups": len(source_audit.get("exact_duplicate_groups", []))},
        ),
        check("model_overlap_periods", overlap_ready, "data/metadata/temporal_overlap_report.json"),
    ]
    ready = all(model["status"] == "READY" for model in models.values()) and all(
        item["passed"] for item in acceptance
    )
    blockers = [item["name"] for item in acceptance if not item["passed"]]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase01_status": "COMPLETE" if ready else "PARTIAL",
        "final_decision": "READY FOR PHASE 02" if ready else "PHASE 01 NOT COMPLETE",
        "models": models,
        "acceptance_gate": acceptance,
        "genuine_blockers": blockers,
    }
    temporary = OUTPUT.with_name(OUTPUT.name + ".part")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(json.dumps({"phase01_status": report["phase01_status"], **{key: value["status"] for key, value in models.items()}, "blockers": blockers}, indent=2))
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
