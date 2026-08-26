# Operational Intelligence Contract (Phase 03 → Phase 04)

**Version:** 1.0.0 · **Producer:** `operational/` package · **Status:** stable for Phase 04 consumption

This is the stable contract Phase 04 (API/product integration) builds against. Phase 04 should
**not** recompute risk, exposure, warning eligibility, or recommended actions — it consumes the
records this pipeline already produced and adapts/serves them.

## Where records live

```
data/operational/intelligence/<track>/<as_of_date>.json   # full records, one per geography unit
data/operational/warnings/<track>/<as_of_date>.json       # subset where warning.eligible == true
data/operational/exposure/<track>/<as_of_date>.csv        # flat exposure table for the same run
data/operational/summary/national_summary_<date>.json     # unit counts by severity, no averaged probabilities
data/operational/summary/latest_run_summary.json          # most recent pipeline run's full summary
data/operational/replay/<track>_operational_replay.csv.gz # historical replay, full test partition
```

`track` is one of `drought`, `flood`, `food_security`. `as_of_date` is `YYYY-MM-DD`.

## Record schema

Every record has exactly these top-level keys (enforced by
`operational/tests/test_phase03.py::IntelligenceRecordTests::test_record_schema_has_all_contract_fields`):

```json
{
  "intelligence_id": "131abf64cd81830c8fa630e0",
  "risk_type": "FLOOD",
  "as_of_date": "2025-12-28",
  "valid_from": "2025-12-29",
  "valid_until": "2025-12-31",
  "prediction_horizon": "1-3 days",
  "geography": {"type": "STATION", "id": "SH004", "name": "SH004 (Jowhar)", "parent_region_id": "SO21"},
  "station_code": "SH004",
  "river_name": "Shabelle",
  "prediction": {
    "probability": 0.82,
    "risk_level": "WARNING",
    "threshold_version": "flood-1.1.0",
    "risk_thresholds": {"watch": 0.115, "warning": 0.23, "severe": 0.615}
  },
  "exposure": {
    "scope_type": "STATION",
    "population_context": 205986.7,
    "population_potentially_exposed": null,
    "exposure_method": "station_operational_context_only_no_validated_inundation_geometry",
    "exposure_uncertainty": "...",
    "population_source": "worldpop_derived_phase01_population_summary",
    "population_year": 2025,
    "linked_district_id": "SO2101",
    "linked_district_name": "Jowhar"
  },
  "impact_summary": {"signal": "RIVERINE_THRESHOLD_EXCEEDANCE", "station": "SH004", "river": "Shabelle", "level_condition": "above normal", "rate_of_rise_3d": "above normal", "antecedent_rainfall_7d": "above normal", "antecedent_soil_wetness": "above normal"},
  "drivers": [{"feature": "level_ratio_moderate", "observed_value": 0.94, "training_median": 0.41, "probability_change_if_replaced_by_training_median": 0.31, "reason_code": "RIVER_LEVEL_NEAR_THRESHOLD"}],
  "warning": {"eligible": true, "status": "CANDIDATE", "suppression_reason": null, "reason_codes": ["RIVER_LEVEL_NEAR_THRESHOLD"]},
  "recommended_actions": [{"action_id": "FLOOD-WARNING-01", "status": "REQUIRES_REVIEW", "...": "..."}],
  "data_quality": {"model_input_quality": "GOOD", "feature_availability": 1.0, "out_of_range_features": [], "freshness": {"status": "GOOD", "...": "..."}, "overall_status": "GOOD"},
  "model": {"id": "flood-early-warning", "version": "1.1.0", "algorithm": "logistic_regression", "calibration_method": "isotonic"},
  "lineage": {"dataset_version": "1.1.0", "dataset_checksum_sha256": "...", "feature_version": "1.1.0", "target_version": "1.1.0", "threshold_version": "1.1.0", "action_catalogue_version": "1.0.0", "pipeline_version": "1.0.0", "as_of_date": "2025-12-28"},
  "limitations": ["Riverine early warning for five supported Jubba/Shabelle gauges only; not Somalia-wide, not flash/surface flood.", "..."],
  "generated_at": "2026-08-26T12:00:00+00:00"
}
```

`risk_level` may also be `"UNKNOWN"` when `data_quality.model_input_quality == "INSUFFICIENT"` —
in that case `prediction.probability` is `null` and `exposure`/`impact_summary` are withheld
(`exposure_method: "withheld_insufficient_data_quality"`), never a guessed value.

## Scope enforcement Phase 04 must preserve

- **Drought:** `geography.type` is always `"DISTRICT"`. Never request or fabricate a prediction for a
  district outside `operational.geography.registry().drought_supported_districts` (87 real districts;
  `"Unspecified"` is present in that set but explicitly rejected as ungeographic — never surface it).
- **Flood:** `geography.type` is always `"STATION"`. Only `SH001`, `SH002`, `SH004`, `JB001`, `JB009`
  exist. Do not imply Somalia-wide or flash-flood coverage from this data. `scope_type` inside
  `exposure` is always `"STATION"` for flood — never silently upgrade it to district/region coverage.
- **Food security:** `geography.type` is always `"REGION"`. Never request or render a
  district-level food-security prediction; there is no validated methodology for that
  disaggregation. If a future UI needs district context, it must be presented as *inherited from the
  region*, explicitly labeled as such — not as a district-model output.

## National / summary view rules

`data/operational/summary/national_summary_<date>.json` reports **unit counts by severity per
track**, plus population context totals. It never reports a single national probability. Phase 04
must not average heterogeneous per-unit probabilities into one number (e.g., "Somalia flood
probability = 73%") — there is no validated methodology for that aggregation, and the summary output
intentionally excludes it. Aggregate at most to counts (`number of WATCH+ districts`,
`number of WARNING+ stations`, etc.) or population-context sums, matching what `national_summary`
already computes.

## Audit fields

Every record already carries `lineage` (dataset/feature/target/threshold/action-catalogue/pipeline
versions, checksum, `as_of_date`) and `generated_at`. `intelligence_id` is a deterministic SHA-256
hash of `(risk_type, geography_id, as_of_date, model_version, dataset_checksum)` — re-running the
pipeline with the same inputs reproduces the same id (verified by the idempotency test and by
`data/scripts/phase03_validate.py`'s two-run diff). Phase 04's audit/publication workflow can use
`intelligence_id` as a stable foreign key without needing to recompute anything.

## What Phase 04 still needs to build

This contract intentionally stops short of:

- **Human review workflow** — `warning.status` reaches `CANDIDATE` at most; there is no
  `ACKNOWLEDGED`/`PUBLISHED` state machine, no reviewer identity, no approval audit trail. Phase 04
  owns that.
- **Action approval** — every action's `status` is `SUGGESTED` or `REQUIRES_REVIEW`, never
  `APPROVED`. Phase 04's workflow assigns approval.
- **Live feature ingestion** — the pipeline reads the frozen Phase 01/02 historical feature archive
  (`data/model_ready/<track>/`). Streaming/live feature updates are out of scope here; Phase 04 (or a
  later phase) must decide how new source data flows into that archive before `as_of_date` runs can
  reflect "today" in production.
- **API surface** — this contract defines the payload; Phase 04 defines routes, auth, pagination, and
  the mapping onto the existing `backend/` FastAPI service's own domain model (see "Backend
  integration note" below).

## Frontend-consumable fields (map/dashboard)

A future frontend needs, per record: `geography` (for map placement/labeling), `prediction.risk_level`
and `prediction.probability` (for color/severity), `prediction_horizon` and `valid_from`/`valid_until`
(for time context), `exposure.population_context` and `population_potentially_exposed` (rendered with
distinct labels — never merged into one "affected" number), `drivers` (for a "why" panel),
`warning.status` (to distinguish an actionable candidate from a suppressed one),
`recommended_actions` (grouped by `status`), `data_quality.overall_status` and `.freshness.status`
(to visually flag stale/degraded tiles), `model.version`, and `limitations` (should be visible near
any risk display, not buried).

## Backend integration note

`backend/app/modules/{exposure,risks,early_actions,ml_registry}` already define a separate,
UUID/`admin_unit_id`-keyed domain model (see `backend/app/core/enums.py`) that is not yet wired to
real Phase 01/02 data. Phase 03 deliberately did not modify that scaffold — doing so would be a
redesign, outside this phase's scope. Phase 04's job is to write an adapter that maps this contract's
`risk_type`/`risk_level`/canonical ids onto that schema (e.g., `RiskLevel.WARNING` ↔ this contract's
`"WARNING"`, `RiskDomain.RIVER_FLOOD` ↔ `risk_type: "FLOOD"`, canonical `district_id`/`region_id`/
`station_code` ↔ `admin_unit_id` via the Phase 01 geographic crosswalk) — not to re-derive risk,
exposure, or actions from scratch.

## Serialization guarantee

Every record round-trips through `json.dumps(record, allow_nan=False)` without error — no NaN,
Infinity, numpy scalar, or non-serializable object ever reaches these files
(`ml.common.finite_or_none` is applied before every write; enforced by
`IntelligenceRecordTests::test_record_is_strictly_json_serializable`).
