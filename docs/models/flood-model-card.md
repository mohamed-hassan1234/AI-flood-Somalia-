# Flood Model Card

**Model ID:** `flood-early-warning` · **Version:** 1.1.0 · **Status:** VALIDATED

## Purpose

**Riverine flood early-warning model for five supported Jubba/Shabelle monitoring corridors.** It
predicts whether a gauge will meet or exceed its official moderate river-level threshold within the
next 1–3 days. It does **not** represent flash/surface flooding and does **not** cover any Somalia
district beyond these five gauges. Broader Somalia flood-risk coverage would require remote-sensing
or event-based labels not present in the Phase 01 foundation.

## Target

- **Target:** `riverine_moderate_threshold_exceedance_within_3_days`
- **Unit of prediction:** one of SH001 (Belet Weyne), SH002 (Bulo Burti), SH004 (Jowhar), JB001
  (Luuq), JB009 (Dollow) — FAO SWALIM/SNRFA gauges
- **Prediction horizon:** days t+1 through t+3
- **Positive:** max observed level on t+1..t+3 ≥ station moderate threshold
- **Negative:** all three future daily levels observed and below threshold
- **Unknown (excluded):** any required future day missing
- Full contract: `ml/config/targets.json` / `docs/phase-02-target-definitions.md`

## Data

- **Dataset:** `data/model_ready/flood/flood_dataset_v1.1.0.csv.gz` (17,632 rows, sha256
  `587b3fadeaa70df0f23c6f8317334a5afad608643d5161ba3ff2c63743850788`)
- **Temporal coverage:** 2015-01-08 – 2025-12-29
- **Geography:** 5 gauges only
- **Class balance:** 1,665 positive / 15,967 negative (9.4% positive rate); 1,749 rows excluded as
  unknown future window

## Features (19)

`current_level_m, level_change_1d, level_change_3d, level_change_7d, level_mean_7d, level_max_7d,
level_ratio_moderate, distance_to_moderate_m, distance_to_high_m, distance_to_bankfull_m,
rain_1d_mm, rain_3d_mm, rain_7d_mm, rain_30d_mm, heavy_rain_days_7d, gwet_top_7d, gwet_top_30d,
gwet_root_30d, t2m_7d_c`

Future level is label metadata only; every feature window ends at `feature_as_of_date`.

## Partitions

| Split | Period | Rows | Positive |
|---|---|---|---|
| Train | 2015–2020 | 10,791 | 1,045 |
| Validation | 2021–2022 | 2,806 | 47 |
| Test (untouched until final evaluation) | 2023–2025 | 4,035 | 573 |

## Algorithm and selection

Candidates: a threshold/rise/rainfall rule baseline, logistic regression (balanced class weights),
random forest. **Selected: logistic regression** — random forest's validation utility gain was under
the predeclared 0.02 threshold, so the simpler model was retained.

## Calibration

Isotonic regression fit on validation only. Validation Brier improved 0.0275 → 0.0032; test Brier
improved 0.0771 → 0.0354; test ECE improved 0.0983 → 0.0309.

## Operating thresholds

- **Operating threshold:** 0.23
- **Risk levels:** WATCH ≥ 0.115, WARNING ≥ 0.23, SEVERE ≥ 0.615

## Final test-period metrics (2023–2025, evaluated once)

| Metric | Value |
|---|---|
| Recall | 0.789 |
| Precision | 0.902 |
| F1 | 0.842 |
| ROC-AUC | 0.971 |
| PR-AUC | 0.880 (6.2× the 0.142 test prevalence) |
| Brier (calibrated) | 0.035 |
| False alarm rate | 0.014 |
| Miss rate | 0.211 |

## Rolling backtest — reported per station, never averaged away

6 expanding-window folds, `ml/artifacts/flood/rolling_backtest_predictions.csv.gz` (9,995
predictions), pooled recall 0.856, false alarm rate 0.016, mean detected lead time 1.04 days.
**Per-station breakdown** (`ml/artifacts/flood/station_backtest.json`, computed directly from the
frozen backtest predictions):

| Station | Rows | Positives | Recall | Precision | False alarm rate | Mean lead time (days) |
|---|---|---|---|---|---|---|
| SH001 (Belet Weyne) | 1,998 | 448 | 0.904 | 0.967 | 0.009 | 1.02 |
| SH002 (Bulo Burti) | 2,182 | 239 | 0.824 | 0.956 | 0.005 | 1.02 |
| SH004 (Jowhar) | 2,019 | 339 | 0.873 | 0.871 | 0.026 | 1.03 |
| JB001 (Luuq) | 2,003 | 59 | 0.797 | 0.610 | 0.015 | 1.15 |
| JB009 (Dollow) | 1,793 | 128 | 0.727 | 0.679 | 0.026 | 1.14 |

The Jubba corridor stations (JB001, JB009) detect events reliably but with materially lower
precision than the Shabelle stations — flagged as a known limitation, not smoothed over by pooling.

## Explainability

SHAP not applicable (linear final model). Global: permutation importance. Local: median-perturbation
attribution per prediction. See `ml/artifacts/flood/explainability.json`.

## Feature drift

`ml/artifacts/flood/feature_drift.json` — PSI computed train→validation and train→test for every
feature; no feature shows drift severe enough to indicate a pipeline break.

## Known limitations

- **Geographic scope:** five gauges on the Jubba/Shabelle corridors only — not a Somalia-wide flood
  product, and not a substitute for flash/surface flood monitoring.
- **Station heterogeneity:** JB001/JB009 precision is materially lower than the Shabelle stations;
  treat Jubba-corridor WARNING outputs with more scrutiny.
- **Lead time:** ~1 day mean detected lead time — short by design, since the target horizon is
  1–3 days; do not present this as a multi-day advance warning system.
- **Validation-period rarity:** only 47 positive validation rows (extreme rarity in 2021–2022);
  calibration and threshold selection carry more sampling uncertainty than the drought/food tracks.

## Reproduction

```
python -m ml.pipeline run
python data/scripts/phase02_validate.py
```

Artifact: `ml/artifacts/flood/flood_model_v1.1.0.joblib`
(sha256 `7d5db090b3601734be8ac6625abcaffcdb340e11f4bdbb0f9a36c635541bed80`).

## Retraining guidance

Retrain when new gauge seasons complete or after any change to official station thresholds.
Recompute the per-station backtest every retrain; do not accept a pooled metric alone.
