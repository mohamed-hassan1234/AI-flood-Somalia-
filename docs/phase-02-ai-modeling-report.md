# Phase 02 — AI / Predictive Intelligence Modeling Report

**Status:** COMPLETE · **Version:** 1.1.0

This report documents Phase 02 of the Somalia AI Food Security, Drought & Flood Early Warning
Platform: three independent, time-aware, calibrated, explainable early-warning model tracks built
on the validated Phase 01 data foundation. It does not repeat Phase 01 and does not begin Phase 03.

## 1. Objectives

Build and honestly evaluate three separate model tracks — drought, flood, food security — each with
its own target, dataset, baseline, candidate models, historical backtest, calibration, and
explainability, so that Phase 03 can consume a stable inference contract rather than raw model code.

## 2. Phase 01 inputs used

Read before any Phase 02 code was written: `data/metadata/phase01_completion_report.json`,
`phase01_readiness.json`, `phase01_validation_report.json`, `docs/temporal-alignment-strategy.md`,
`data/metadata/source_registry.json`, `data_availability_matrix.csv`,
`temporal_coverage_matrix.csv`, `geographic_crosswalk.csv`, and the processed CHIRPS, MOD13Q1,
NASA POWER, FAO SWALIM/SNRFA river, IPC, and WFP market outputs. No Phase 01 dataset was
re-downloaded or reprocessed; Phase 02 builders read Phase 01's processed outputs and manifests only.

## 3. Target definitions

Full specification: `docs/phase-02-target-definitions.md`, machine-readable contract
`ml/config/targets.json`. Summary:

| Track | Target | Unit | Horizon |
|---|---|---|---|
| Drought | `agricultural_vegetation_stress_next_composite` | canonical district | next MOD13Q1 16-day composite |
| Flood | `riverine_moderate_threshold_exceedance_within_3_days` | 1 of 5 FAO SWALIM/SNRFA gauges | t+1..t+3 |
| Food security | `regional_crisis_or_worse_population_burden_20pct` | canonical OCHA region (IPC L1) | 30 days pre-assessment |

Each target avoids circularity: rainfall is a drought predictor, never the drought label; river
level is a flood predictor at t, never the future label; IPC projections are excluded from labels
and only observed current assessments are used. Unknown labels (absent/QA-null/missing future
observations) are excluded, never coerced to negative — 3,546 drought rows and 1,749 flood rows were
excluded this way.

Target sanity statistics (positive/negative/unknown counts, temporal and geographic distribution,
longest gaps) are in `data/metadata/phase02_target_summary.json`.

## 4. Feature engineering

Rainfall (CHIRPS): 7/30/90-day totals, heavy-rain-day counts, dry-spell/dry-day counts — all windows
end at `feature_as_of_date`. Vegetation (MOD13Q1): last NDVI/EVI, 1-composite NDVI change, valid
pixel fraction (MODIS QA respected — strict-QA nulls are never filled as healthy vegetation), and a
district/seasonal-slot NDVI anomaly z-score referenced against 2015–2020 only. Climate (NASA POWER):
7/30-day temperature means and maxima, 7/30-day surface and root-zone soil wetness (`gwet_top`,
`gwet_root`). River (FAO SWALIM/SNRFA): current level, 1/3/7-day change, 7-day mean/max, distance to
moderate/high/bankfull thresholds. Markets (WFP): 90-day median price, 90-day and 365-day price
change/anomaly. IPC: previous observed Phase 3+ percentage, used only when its validity period ended
on or before the as-of date. Static: log-transformed region population.

## 5. Dataset construction

Reusable builders in `ml/pipeline.py` (no ad hoc CSV joins) produce versioned, checksummed outputs
under `data/model_ready/<track>/`, each with a paired `metadata_v1.1.0.json` (schema, lineage, row
counts, missingness) and `feature_schema_v1.1.0.json`.

| Track | Rows | Features | Coverage | Positive rate | Max feature missingness |
|---|---|---|---|---|---|
| Drought | 17,433 | 16 | 2015-01-17 – 2025-12-19, 88 districts | 12.7% | 4.0% |
| Flood | 17,632 | 19 | 2015-01-08 – 2025-12-29, 5 gauges | 9.4% | 0.5% |
| Food security | 378 | 15 | 2017-01-01 – 2025-07-01, 18 regions | 41.5% | 32.0% (market features only) |

## 6. Leakage prevention

`ml/pipeline.py::leakage_audit` independently re-derives, per track: every feature timestamp is not
future-dated relative to `feature_as_of_date`; the target period always starts after the as-of date;
observation keys are unique; no feature column encodes the target or contains "future"; and the
frozen train/validation/test partitions are strictly time-ordered with no overlap. Result:
`data/metadata/phase02_leakage_report.json` — **PASS on all three tracks, all checks**. A failing
leakage audit blocks training entirely (`run_phase02()` raises before any model is fit).

## 7. Missing-data handling

Missingness is retained with explicit indicators inside each track's training-only preprocessing;
no statistic used for imputation is ever learned from validation or test data. Strict-QA vegetation
nulls and unresolved market coverage are left missing rather than zero-filled. Per-feature
missingness fractions are recorded in each track's dataset metadata.

## 8. Baselines

Each track has a deterministic, interpretable rule baseline evaluated **before** any statistical or
ML candidate (Rule 7): drought (rainfall/wetness/vegetation composite score), flood
(threshold-ratio/rise/rainfall rule), food security (previous-IPC-persistence/market rule). See
`ml/artifacts/<track>/baseline_metrics.json` and `ml/estimators.py::baseline_probability`.

## 9. Advanced models and selection

Candidates: logistic regression (`class_weight="balanced"`) and random forest (bounded depth,
`class_weight="balanced_subsample"`) for every track, scored on the validation partition by a
utility function combining PR-AUC and calibration behavior. **Drought and flood selected logistic
regression**; **food security selected the rule baseline** — in every case because the runner-up
gained less than the predeclared 0.02 validation-utility margin over the simpler choice (Rule 7,
Rule 43, Rule 57: *"If advanced ML fails to outperform baseline meaningfully, use the baseline."*).
Full candidate parameters and validation metrics: `ml/artifacts/<track>/candidate_metrics.json`.

## 10. Hyperparameter tuning

Bounded, not exhaustive: fixed random forest depth/leaf-size grid, `random_state=20260826`
throughout, tuned and selected against validation only. No tuning ever touched the final test
partition.

## 11. Validation methodology

Fixed chronological outer partitions, frozen before any final-test inspection:

| Track | Train | Validation | Untouched final test |
|---|---|---|---|
| Drought | 2015–2020 | 2021–2022 | 2023–2025 |
| Flood | 2015–2020 | 2021–2022 | 2023–2025 |
| Food security | 2017–2021 | 2022–2023 | 2024–2025 |

No random shuffling across time was used anywhere in Phase 02.

## 12. Historical backtesting

Rolling expanding-window backtests (`ml/pipeline.py::rolling_backtest`), fold count per track:
drought 5, flood 6, food security 4 — each fold trains through year T, calibrates/selects a
threshold on year T+1, and scores year T+2, simulating what the platform would actually have known.
Pooled + per-fold results: `ml/artifacts/<track>/backtest_summary.json` and
`ml/artifacts/<track>/rolling_backtest_predictions.csv.gz`.

**Flood is reported per station, never pooled away** (`ml/artifacts/flood/station_backtest.json`,
computed by `data/scripts/phase02_validate.py` directly from the frozen backtest predictions):

| Station | Recall | Precision | False alarm rate |
|---|---|---|---|
| SH001 | 0.904 | 0.967 | 0.009 |
| SH002 | 0.824 | 0.956 | 0.005 |
| SH004 | 0.873 | 0.871 | 0.026 |
| JB001 | 0.797 | 0.610 | 0.015 |
| JB009 | 0.727 | 0.679 | 0.026 |

The Jubba stations (JB001, JB009) are measurably weaker on precision than the Shabelle stations —
reported explicitly rather than hidden by averaging (Rule/§35).

## 13. Historical event replay

`ml/artifacts/<track>/historical_replay.csv.gz` replays the **entire untouched final-test period**
(not a hand-picked subset of "successful" events) with feature-as-of date, target period, observed
outcome, predicted probability, prediction, and correctness — the strongest form of documented,
non-cherry-picked selection criterion available (Rule 67: no manual cherry-picking).

## 14. Failure analysis

`ml/artifacts/<track>/failure_analysis.json` lists the highest-confidence false positives and false
negatives and an error breakdown by region. Drought errors concentrate in the southern agropastoral
regions (SO21–SO28) where vegetation variability is highest; no single region or season dominates
disproportionately.

## 15. Calibration

Validation-only calibration via `ml/common.py::fit_calibrator`, choosing among identity/sigmoid/
isotonic by validation Brier, with a prevalence-shift guard (max 0.25 absolute shift) that forces
identity calibration when the validation event rate differs too much from the reference rate to be
scientifically trustworthy — the food-security track hit this guard (0.581 shift) and correctly
avoided a bad calibration fit rather than forcing one.

| Track | Method | Validation Brier before → after | Test Brier before → after |
|---|---|---|---|
| Drought | isotonic | 0.1639 → 0.1174 | 0.1075 → 0.0649 |
| Flood | isotonic | 0.0275 → 0.0032 | 0.0771 → 0.0354 |
| Food security | identity (guarded) | 0.2013 → 0.2013 | 0.2022 → 0.2022 |

## 16. Threshold selection

Operating thresholds are chosen on validation by maximizing F1 subject to a minimum-recall floor,
not fixed at 0.5. Four-level risk output (NORMAL/WATCH/WARNING/SEVERE) is derived per track from the
calibrated probability distribution: drought WATCH 0.135 / WARNING 0.27 / SEVERE 0.635; flood WATCH
0.115 / WARNING 0.23 / SEVERE 0.615; food security WATCH 0.265 / WARNING 0.53 / SEVERE 0.765.

## 17. Explainability

SHAP is not applicable to any final selected model (drought and flood select linear logistic
regression; food security selects a deterministic rule) — this is stated explicitly rather than
fabricating tree-based SHAP output. Global explanations use permutation importance (scoring =
average precision); local, per-prediction explanations use median-perturbation attribution — both
implemented once in `ml/common.py::global_and_local_explanations` and reused by all three tracks.
See `ml/artifacts/<track>/explainability.json`.

## 18. Final model selection

| Track | Selected | Reason |
|---|---|---|
| Drought | Logistic regression | Beat the rule baseline materially; random forest's validation gain was below the 0.02 threshold |
| Flood | Logistic regression | Same pattern — simpler model preferred when the gain from complexity is negligible |
| Food security | Rule baseline | Neither logistic regression nor random forest cleared the 0.02 validation-utility margin |

## 19. Metrics (final test period, evaluated once)

| Track | Recall | Precision | ROC-AUC | PR-AUC (vs. prevalence) | Brier | FAR |
|---|---|---|---|---|---|---|
| Drought | 0.616 | 0.364 | 0.869 | 0.386 (4.6×) | 0.065 | 0.098 |
| Flood | 0.789 | 0.902 | 0.971 | 0.880 (6.2×) | 0.035 | 0.014 |
| Food security | 0.538 | 0.700 | 0.741 | 0.681 (1.9×) | 0.202 | 0.130 |

Full registry: `ml/reports/model_metrics_registry.json` / `.csv`.

## 20. Acceptance gate results

Predeclared before final-test inspection in `ml/config/acceptance.json`, evaluated by
`data/scripts/phase02_validate.py`, and never adjusted after seeing results (Rule 44, Rule 71):

| Track | Status |
|---|---|
| Drought | **VALIDATED** |
| Flood | **VALIDATED** |
| Food security | **VALIDATED** |

Full per-check results, flood station breakdown, and the complete Phase 02 checklist:
`data/metadata/phase02_completion_report.json`.

## 21. Limitations

1. **Flood scope** is five Jubba/Shabelle gauges only, not Somalia-wide flood risk, and not flash
   flood risk. See the flood model card.
2. **Food-security scope** is IPC Level 1 region, not district; no district disaggregation is
   claimed.
3. **Drought is environmental**, not humanitarian — a vegetation-stress signal, not a hunger
   prediction.
4. **Small food-security sample** (378 rows, 26 positive test rows) leaves per-fold backtest metrics
   with real sampling uncertainty.
5. **Jubba-corridor flood precision** (JB001/JB009) is materially weaker than the Shabelle stations.
6. **Food-security calibration** is intentionally left uncalibrated (identity) due to a large
   train/validation prevalence shift — this is a documented safeguard, not an oversight.

## 22. Artifacts

Model binaries, calibrators, thresholds, and metadata for each track live under
`ml/artifacts/<track>/`, each with a joblib artifact, `model_metadata.json` (features,
periods, checksum, environment), `thresholds.json`, `inference_contract.json`, and
`explainability.json`. Every artifact records a SHA-256 checksum and a confirmed serialization
round trip (`serialization_round_trip_passed: true`).

## 23. Reproduction

```
python data/scripts/phase01_validate.py     # confirm Phase 01 foundation (already complete)
python -m ml.pipeline build                 # build datasets + leakage audit only
python -m ml.pipeline run                   # full: datasets → baselines → candidates →
                                             #   calibration → thresholds → backtest → explain
python ml/tests/run_tests.py                # automated test suite
python data/scripts/phase02_validate.py     # acceptance gate + completion report
```

Environment pinned in every artifact's metadata: Python 3.13.5, numpy 2.3.5, pandas 2.3.3,
scikit-learn 1.9.0, joblib 1.5.3, `random_seed=20260826`.

## 24. Phase 03 integration recommendations

- Consume `ml/artifacts/<track>/inference_contract.json` as the stable input/output schema; do not
  import model internals directly.
- Surface `data_quality` (GOOD/DEGRADED/INSUFFICIENT) separately from `probability`/`risk_level` in
  any UI — an INSUFFICIENT-quality prediction must never render with a confident risk level.
- Respect the flood station scope and food-security regional scope explicitly in any map or district
  view; do not silently interpolate to unsupported geographies.
- Re-run `data/scripts/phase02_validate.py` after every retrain before promoting a new model
  version; treat a non-VALIDATED status as a deployment blocker.

## Methodological references

FEWS NET and IPC Technical Manual guidance on Crisis-or-worse population thresholds; WMO guidance on
meteorological vs. agricultural drought definitions; FAO SWALIM operational river-gauge threshold
conventions. No third-party tutorial code was copied; all pipeline code in `ml/` is original to this
repository.
