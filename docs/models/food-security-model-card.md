# Food Security Model Card

**Model ID:** `food_security-early-warning` · **Version:** 1.1.0 · **Status:** VALIDATED

## Purpose

Predicts, 30 days before an observed current IPC validity period starts, whether at least 20% of a
canonical region's population will be in IPC Phase 3 or worse (Crisis-or-worse). This
operationalizes a *high regional Crisis-or-Worse burden* signal — it is **not** presented as an
official IPC classification, and the unit of prediction is the IPC Level 1 region, not a district
(Phase 01's IPC-to-district geographic mapping is not forced onto this target).

## Target

- **Target:** `regional_crisis_or_worse_population_burden_20pct`
- **Unit of prediction:** canonical OCHA region matched to IPC Level 1 (18 regions; historical IPC
  aliases resolved via the Phase 01 geographic crosswalk)
- **Prediction horizon:** 30 days before the observed current IPC validity period starts
- **Label source:** IPC Level 1 **current** assessment Phase 3+ percentage only — first and second
  projections are excluded from labels to avoid using a forecast as ground truth
- **Positive:** observed current IPC Phase 3+ percentage ≥ 0.20
- **Negative:** observed current IPC Phase 3+ percentage < 0.20
- Full contract: `ml/config/targets.json` / `docs/phase-02-target-definitions.md`

## Data

- **Dataset:** `data/model_ready/food_security/food_security_dataset_v1.1.0.csv.gz` (378 rows,
  sha256 `5c201abe08927794a46721fb26187e49b45e025c6754545874b2146ed1608a33`)
- **Temporal coverage:** 2017-01-01 – 2025-07-01
- **Geography:** all 18 canonical regions
- **Class balance:** 157 positive / 221 negative (41.5% positive rate)
- **Missingness:** market features (`market_usdkg_90d_median`, `market_price_change_previous_90d`,
  `market_price_anomaly_365d`) are ~31–32% missing where WFP market coverage is sparse — retained
  with missingness indicators, never silently zero-filled

## Features (15)

`rain_30d_mm, rain_90d_mm, dry_days_30d, t2m_30d_c, t2m_max_30d_c, gwet_top_30d, gwet_root_30d,
ndvi_last, ndvi_change, vegetation_valid_pixel_fraction, market_usdkg_90d_median,
market_price_change_previous_90d, market_price_anomaly_365d, previous_ipc3plus_percentage,
log_region_population`

`previous_ipc3plus_percentage` is used only when its validity period ended on or before the as-of
date — no assessment ever sees its own future value.

## Partitions

Given the small event count (this track has far fewer independent assessment rounds than the daily
drought/flood tracks), acceptance uses the combined train+validation development pool.

| Split | Period | Rows | Positive |
|---|---|---|---|
| Train | 2017–2021 | 180 | 34 |
| Validation | 2022–2023 | 126 | 97 |
| Test (untouched until final evaluation) | 2024–2025 | 72 | 26 |

## Algorithm and selection

Candidates: a previous-IPC-persistence / market-price rule baseline, logistic regression, random
forest. **Selected: the rule baseline** — neither statistical nor tree-based candidate improved
validation utility by the predeclared 0.02 margin, so per Rule 7/43 the simpler, fully interpretable
baseline was kept in production rather than presenting spurious ML sophistication.

## Calibration

Sigmoid/isotonic were evaluated, but the validation-to-training prevalence shift (0.581, far above
the 0.25 guard) triggered the identity-calibration safeguard in `ml/common.py`: exporting a
calibration fit on a training regime with a materially different event rate than validation would
have been scientifically indefensible, so calibration was correctly left as identity rather than
forcing a fit. Test Brier is unchanged before/after (0.202), which is expected and appropriate under
the guard, not a defect.

## Operating thresholds

- **Operating threshold:** 0.53
- **Risk levels:** WATCH ≥ 0.265, WARNING ≥ 0.53, SEVERE ≥ 0.765

## Final test-period metrics (2024–2025, evaluated once)

| Metric | Value |
|---|---|
| Recall | 0.538 |
| Precision | 0.700 |
| F1 | 0.609 |
| ROC-AUC | 0.741 |
| PR-AUC | 0.681 (1.9× the 0.361 test prevalence) |
| Brier | 0.202 |
| False alarm rate | 0.130 |
| Miss rate | 0.462 |

## Rolling backtest

4 expanding-window folds (one per test year, 2022–2025),
`ml/artifacts/food_security/rolling_backtest_predictions.csv.gz` (198 predictions). Mean detected
lead time: 30 days (the defined horizon). Per-fold recall/false-alarm rate vary substantially by
year (e.g. 2022 recall 1.0 vs. false alarm rate 1.0 on a 17-negative fold) — a direct consequence of
very small yearly negative counts, documented transparently rather than smoothed by pooling.

## Explainability

SHAP not applicable (final model is a deterministic rule, not a fitted estimator in the SHAP sense).
Global and local explanations use the same permutation-importance / perturbation approach as the
other tracks, applied to the rule's continuous score. See
`ml/artifacts/food_security/explainability.json`.

## Known limitations

- **Small sample size:** 378 total rows and only 26 positive test observations is small by ML
  standards; metrics carry real sampling uncertainty, especially per-fold backtest numbers.
- **Regional, not district:** outputs are IPC Level 1 regional signals; do not present as
  district-level food-security classifications without an explicit, separately validated
  disaggregation step in Phase 03.
- **Market data gaps:** ~31% of rows lack market price coverage; those rows rely on the remaining
  environmental features and missingness indicators alone.
- **Baseline in production:** the deployed model is the interpretable rule, not a black-box
  classifier — this is a deliberate, evidence-based choice, not a fallback of last resort.
- **Environmental drought is a predictor here, not a proxy label** — this model is trained directly
  against observed IPC outcomes, so it is the correct place (not the drought model) for any claim
  linking environmental conditions to humanitarian impact.

## Reproduction

```
python -m ml.pipeline run
python data/scripts/phase02_validate.py
```

Artifact: `ml/artifacts/food_security/food_security_model_v1.1.0.joblib`
(sha256 `754a7f00d72f182fa1cf5c3f2b3829c6ca4f487e2a1b632acb4d7d10a5b2c2e0`).

## Retraining guidance

Retrain after each new IPC assessment round. Re-check the calibration prevalence-shift guard every
retrain — do not override it manually to force a calibrated output.
