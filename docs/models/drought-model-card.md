# Drought Model Card

**Model ID:** `drought-early-warning` · **Version:** 1.1.0 · **Status:** VALIDATED

## Purpose

Predicts agricultural vegetation stress in the **next MOD13Q1 16-day composite** for a canonical
Somalia district. This is an environmental/agricultural drought signal, not a humanitarian-impact
or hunger prediction — that link is the separate [food-security model](food-security-model-card.md).

## Target

- **Target:** `agricultural_vegetation_stress_next_composite`
- **Unit of prediction:** canonical district (91 OCHA COD-AB v03 districts)
- **Prediction horizon:** the next MOD13Q1 16-day composite after `feature_as_of_date`
- **Label source:** MOD13Q1 V061 strict-QA NDVI, standardized against a district/seasonal-slot
  reference climatology fixed from 2015–2020 (the outer training era only)
- **Positive:** future composite NDVI anomaly z-score ≤ −1.0
- **Negative:** future composite NDVI anomaly z-score > −1.0
- **Unknown (excluded, never coerced to negative):** composite absent or strict-QA NDVI null
- Full contract: `ml/config/targets.json` / `docs/phase-02-target-definitions.md`

## Data

- **Dataset:** `data/model_ready/drought/drought_dataset_v1.1.0.csv.gz` (17,433 rows, sha256
  `d607aad7d8888ce2cd84a0250cea14766daa6fe7a3c2227f0c8bde74556e33b0`)
- **Temporal coverage:** 2015-01-17 – 2025-12-19
- **Geography:** 88 districts with usable history across 18 regions
- **Class balance:** 2,219 positive / 15,214 negative (12.7% positive rate); 3,546 rows excluded as
  unknown future target
- **Maximum feature missingness:** 4.0% (`ndvi_change_1`); rainfall/POWER features are ≤2.4% missing

## Features (16)

`rain_7d_mm, rain_30d_mm, rain_90d_mm, heavy_rain_days_30d, dry_spell_days, t2m_7d_c, t2m_30d_c,
t2m_max_30d_c, gwet_top_7d, gwet_top_30d, gwet_root_30d, ndvi_last, evi_last, ndvi_change_1,
vegetation_valid_pixel_fraction, ndvi_last_anomaly_z_reference`

Rainfall is a predictor, never a redefinition of the label. Every window ends at
`feature_as_of_date`; the last vegetation composite used as a feature must have ended on or before
that date.

## Partitions (chronological, frozen before final test)

| Split | Period | Rows | Positive |
|---|---|---|---|
| Train | 2015–2020 | 10,164 | 1,151 |
| Validation | 2021–2022 | 3,349 | 740 |
| Test (untouched until final evaluation) | 2023–2025 | 3,920 | 328 |

## Algorithm and selection

Candidates evaluated: a deterministic rainfall/wetness/vegetation rule baseline, logistic
regression (`class_weight="balanced"`, `C=1.0`, seed 20260826), and random forest (250 trees,
`max_depth=8`, `class_weight="balanced_subsample"`). **Selected: logistic regression** — it improved
materially over the rule baseline, while random forest's validation utility gain was under the
predeclared 0.02 threshold, so the simpler, more interpretable model was kept (Rule 7 / Rule 43).

## Calibration

Isotonic regression fit on the validation partition only. Validation Brier improved
0.1639 → 0.1174; test Brier improved 0.1075 → 0.0649; test ECE (10-bin) improved 0.1346 → 0.0324.

## Operating thresholds

- **Operating threshold:** 0.27 (selected on validation via the recall/false-alarm trade-off rule)
- **Risk levels:** WATCH ≥ 0.135, WARNING ≥ 0.27, SEVERE ≥ 0.635

## Final test-period metrics (2023–2025, evaluated once)

| Metric | Value |
|---|---|
| Recall | 0.616 |
| Precision | 0.364 |
| F1 | 0.458 |
| ROC-AUC | 0.869 |
| PR-AUC | 0.386 (4.6× the 0.084 test prevalence) |
| Brier (calibrated) | 0.065 |
| ECE (10-bin, calibrated) | 0.032 |
| False alarm rate | 0.098 |
| Miss rate | 0.384 |

## Rolling backtest

5 expanding-window folds, `ml/artifacts/drought/rolling_backtest_predictions.csv.gz` (3,920
predictions). Mean detected lead time: 16 days (one MOD13Q1 composite). Failure analysis
(`ml/artifacts/drought/failure_analysis.json`) shows errors concentrated in SO21–SO28 (southern
agropastoral regions with the most vegetation variability); no single region dominates error share.

## Explainability

SHAP is **not applicable** (final model is linear, not tree-based). Global explanations use
permutation importance (scoring = average precision); local explanations use median-perturbation
attribution. Top global drivers: `ndvi_last_anomaly_z_reference` (0.285), `ndvi_change_1` (0.042),
`t2m_30d_c` (0.038), `ndvi_last` (0.038), `evi_last` (0.019). The vegetation anomaly feature
dominating importance is expected and monitored — it is a *current* anomaly, not the future label,
and leakage tests independently confirm this.

## Feature drift

Population Stability Index computed train→validation and train→test for every feature
(`ml/artifacts/drought/feature_drift.json`). Only `ndvi_last_anomaly_z_reference` shows meaningful
drift into the test period (PSI 0.41), consistent with a genuinely different vegetation-anomaly
regime in 2023–2025 rather than a pipeline defect — flagged for retraining monitoring.

## Known limitations

- **Environmental, not humanitarian:** this model predicts vegetation stress, not hunger or IPC
  outcomes; see the separate food-security model for that link.
- **Geographic:** districts with sparse history (e.g. `SO22xx` sub-splits, `Unspecified`) have wide
  uncertainty; treat their outputs cautiously.
- **Temporal:** reference climatology is fixed at 2015–2020; a structurally different climate regime
  after 2025 would require climatology refresh, not just retraining.
- **Recall/precision trade-off:** at the WARNING threshold, roughly 4 in 10 true stress events are
  missed (miss rate 0.384); operational users should treat WATCH-level outputs as informative too.

## Reproduction

```
python -m ml.pipeline run
python data/scripts/phase02_validate.py
```

Environment: Python 3.13.5, numpy 2.3.5, pandas 2.3.3, scikit-learn 1.9.0, joblib 1.5.3, seed
20260826. Artifact: `ml/artifacts/drought/drought_model_v1.1.0.joblib`
(sha256 `9125108a58b5370ffd5e1b30000fd75690eda0cdf38621407cff7c29f7ac64ec`).

## Retraining guidance

Retrain when a new MOD13Q1 season completes, when feature PSI drift exceeds ~0.25 on a core
feature, or at minimum annually. Re-freeze train/validation/test periods explicitly; never re-tune
after inspecting a new final test period.
