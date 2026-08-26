# Phase 03 — Impact & Operational Intelligence Report

**Status:** COMPLETE · **Version:** 1.0.0

## 1. Objective

Transform Phase 02's validated model risk into traceable, geographically meaningful, operationally
honest early-warning intelligence: not just "what is the predicted risk" but where, how severe, who
may be exposed, why the warning fired, how good the evidence is, what to consider doing, and which
model/data version produced it — all reproducible and safe for Phase 04 to build on without
recomputing any of this logic.

## 2. Phase 01 dependencies

`data/processed/population/{district,region}_population_2025.csv` (WorldPop-derived),
`data/metadata/river_station_metadata_validation.json` (station→district resolution),
`data/metadata/geographic_crosswalk.csv`, `data/processed/boundaries/*.geojson`. No Phase 01 dataset
was re-downloaded or reprocessed.

## 3. Phase 02 dependencies

Frozen model artifacts `ml/artifacts/<track>/<track>_model_v1.1.0.joblib` (checksum-verified before
every use), `ml/artifacts/<track>/model_metadata.json` (thresholds, feature list, calibration),
`data/model_ready/<track>/<track>_dataset_v1.1.0.csv.gz` (the historical feature archive Phase 03
runs inference against), `ml.pipeline.partition`/`ml.common.ModelBundle` (reused, not reimplemented).
No Phase 02 model was retrained; no threshold was changed.

## 4. Model scopes (preserved, never widened)

- **Drought:** district-level agricultural/vegetation-stress signal, 87 real districts (the
  `Unspecified` bucket is explicitly excluded from operational output). Not a humanitarian-impact
  prediction.
- **Flood:** riverine threshold-exceedance signal for five gauges (SH001, SH002, SH004, JB001,
  JB009) only. Not Somalia-wide, not flash/surface flood.
- **Food security:** region-level (IPC Level 1) Crisis-or-worse burden-threshold signal, 18 regions.
  Not a district classification, not an exact affected-population count.

## 5. Exposure methodology

See `docs/phase-03-exposure-methodology.md`. Summary: drought reports the full district population
as `population_potentially_exposed` at WATCH+ (whole-district approximation, no cropland mask
available); flood and food security report population **context** only —
`population_potentially_exposed` is always `null` for both, since neither a validated inundation
geometry nor a validated population-fraction methodology exists. This is enforced by automated tests,
not just documentation.

## 6. Population methodology

WorldPop-derived, 2025 reference year, loaded once per process from the Phase 01 summary tables
(`operational/geography.py`). No historical population back-series exists, so replay records over
2015–2025 use the same 2025 figure — a documented simplification.

## 7. Geographic impact methodology

`operational/geography.py::GeographyRegistry` is the single canonical geography layer: district and
region lookups from the Phase 01 population tables, and station→district resolution read directly
from the Phase 02 flood dataset's own `canonical_district_id`/`river` columns (already resolved via
the Phase 01 crosswalk — Phase 03 does not re-derive station geography heuristically). Regional
drought summaries (`data/operational/summary/`) report unit counts by severity and population-context
totals, never an averaged "regional probability."

## 8. Risk → impact transformation

`operational/intelligence.py::build_record` is the single function producing the shared schema across
all three tracks: inference (frozen bundle) → risk level (frozen thresholds) → geography → exposure →
structured `impact_summary` (condition labels derived from the bundle's own training quantiles, never
free text as source of truth) → drivers (median-perturbation local explanation, reused from the
Phase 02 approach) → reason codes → data quality/freshness → warning decision → recommended actions →
lineage. See the full schema in `docs/contracts/operational-intelligence-contract.md`.

## 9. Warning thresholds

Identical to Phase 02, read at runtime from `model_metadata.json`, never hardcoded a second time.
Verified equal by `RiskThresholdTests` and by `data/scripts/phase03_validate.py`.

## 10. Warning policy

See `docs/phase-03-warning-action-policy.md`. Risk level and warning workflow status are distinct
fields; `INSUFFICIENT` data quality or `STALE_CRITICAL` freshness always suppresses eligibility
regardless of how high the underlying probability is.

## 11. Data-quality gates

Two-signal worst-of gate: Phase 02's own feature-availability/range check, combined with a new
Phase 03 freshness check per source. `INSUFFICIENT` overall quality withholds probability/risk_level/
exposure/impact_summary from the record rather than showing a guessed value.

## 12. Freshness policy

Per-source cadence-derived limits (`operational/config/freshness_policy.json`) — 2 days for the
fast-moving river gauge, 3 days for daily rainfall/climate, 32 days for the 16-day MODIS composite,
120–220 days for the sparser market/IPC sources. No single global threshold was invented.

## 13. Recommended-action framework

`operational/config/action_catalog.json` (version 1.0.0): 24 pre-defined, traceable, severity- and
risk-specific actions across the three tracks. Every action is looked up, never generated on the fly.
See `docs/phase-03-warning-action-policy.md` for the full policy and category breakdown.

## 14. Action governance

Actions are emitted with status `SUGGESTED` or `REQUIRES_REVIEW` only — never `APPROVED`.
High-impact/public actions (authority notification, evacuation-route review, public communication,
SEVERE-level escalation) are always `REQUIRES_REVIEW`. No action text orders an evacuation or claims
a distribution has occurred (tested).

## 15. Historical replay

See `docs/phase-03-historical-replay-report.md`. Full operational chain replayed over every row of
the frozen Phase 02 final-test partition per track (3,875 drought / 4,035 flood / 72 food-security
rows). At the warning threshold, replay recall/precision/false-alarm-rate reproduce the Phase 02
model-card numbers almost exactly (the small drought difference is the deliberate `Unspecified`
exclusion) — a strong internal-consistency proof that the operational wrapper introduced no drift.
Flood is reported per station, including the weaker SH004 case; food security's smaller sample and
lower watch-threshold precision are shown, not hidden.

## 16. End-to-end pipeline

`python -m operational.pipeline --as-of-date YYYY-MM-DD [--tracks drought flood food_security]`
(`operational/pipeline.py`). Stages: `FEATURES_READY → MODEL_LOADED → INFERENCE_COMPLETE →
EXPOSURE_COMPLETE → WARNING_EVALUATED → ACTIONS_ATTACHED → OUTPUT_VALIDATED`, logged per track in
every run summary. Writes `data/operational/{intelligence,warnings,exposure,summary}/`.

## 17. As-of-date execution

`operational/pipeline.py::select_latest_as_of` selects, per geography unit, the most recent feature
row on or before `as_of_date` from the frozen historical archive — the same function serves live-style
runs (omit `--as-of-date` to use the latest available date per track) and historical replay/backtesting.
No row with `feature_as_of_date > as_of_date` is ever selected (tested).

## 18. Lineage

Every record's `lineage` block carries dataset version + SHA-256 checksum, feature version, target
version, threshold version, action-catalogue version, pipeline version, and `as_of_date`. The pipeline
run summary additionally carries the git commit. `intelligence_id` is a deterministic hash of
`(risk_type, geography_id, as_of_date, model_version, dataset_checksum)`.

## 19. Reproducibility

The pipeline was run twice at the same `as_of_date` (2024-05-01); intelligence records were byte-identical
after stripping only the `generated_at` timestamp (87/5/18 drought/flood/food-security records,
respectively — the count reflects the `Unspecified` exclusion). See `data/metadata/phase03_completion_report.json::reproducibility`
for the automated version of this check, run by `data/scripts/phase03_validate.py` on every invocation.

## 20. Testing

33 automated tests (`operational/tests/test_phase03.py`) covering geography scope enforcement,
exposure semantics (flood/food-security exposed population always null), risk-threshold fidelity,
warning-policy gating, freshness computation (including a real-archive no-negative-gap check),
action-catalogue coverage and governance, full-schema/serialization/lineage/idempotency of built
records, model-checksum tamper rejection, and replay-partition fidelity to the frozen Phase 02 split.
All 33 pass. See `data/metadata/phase03_test_report.json`.

## 21. Performance

Full pipeline run across all three tracks (as-of-date = latest available, 87+5+18 = 110 geography
units, drivers computed for every record): ~19 seconds. Full historical replay (drivers skipped for
volume, 3,875+4,035+72 = 7,982 rows): drought ~60s, flood ~37–60s, food security <1s. No premature
optimization was performed; these are all well within an operational batch-job budget.

## 22. Known limitations

1. No validated flood inundation/exposure geometry exists; `population_potentially_exposed` is
   permanently `null` for flood — by design, not a defect.
2. Food-security `population_potentially_exposed` is permanently `null`; the model predicts a binary
   burden threshold, not a population fraction.
3. Drought exposure is a whole-district approximation; no sub-district/cropland mask was available.
4. The operational pipeline runs against the frozen Phase 01/02 historical feature archive; live/
   streaming feature ingestion is out of scope for Phase 03.
5. Population is fixed at the 2025 WorldPop reference year for all historical replay records.
6. The `Unspecified` Banadir residual bucket is excluded from operational output (documented, not
   silent — `skipped_unsupported_geography` is reported in every run).
7. Food-security replay sample (72 rows) is small; sub-annual/sub-regional breakdowns are not
   statistically meaningful.

## 23. Integration contract

`docs/contracts/operational-intelligence-contract.md` — full schema, scope-enforcement rules,
national-summary aggregation rules, audit fields, frontend-consumable field list, and an explicit
note on how Phase 04 should adapt this contract onto the existing (currently unwired)
`backend/app/modules/{exposure,risks,early_actions,ml_registry}` scaffold without rewriting Phase 03
logic.

## 24. Phase 04 recommendations

- Build an adapter/ingestion service that reads `data/operational/intelligence/` and maps it onto
  `backend/`'s existing domain model (see the contract's "Backend integration note"); do not
  re-derive risk, exposure, or actions.
- Implement the human-review workflow (`CANDIDATE → ACKNOWLEDGED → PUBLISHED`) and action approval;
  Phase 03 stops at `CANDIDATE`/`SUGGESTED`/`REQUIRES_REVIEW` deliberately.
- Design a live/streaming feature-ingestion path so `as_of_date` runs can reflect true "today" data;
  Phase 03's archive is historical-batch only.
- Preserve every scope boundary (district/station/region) verbatim in any API or map component.

## 25. Reproduction commands

```
python -m ml.pipeline run                        # confirm frozen Phase 02 artifacts (already complete)
python -m operational.pipeline                    # run at the latest available as-of-date per track
python -m operational.pipeline --as-of-date 2024-05-01   # historical/backfill-style run
python -m operational.replay                      # full operational historical replay
python -m operational.tests.run_tests             # automated Phase 03 test suite
python data/scripts/phase03_validate.py           # acceptance gate + completion/validation reports
```
