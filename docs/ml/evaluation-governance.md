# Model evaluation governance

`GET /api/v1/outcomes/models/{model_version_id}/metrics` is an Internal projection requiring
`models.evaluate`. Results are filtered to the evaluator's national or descendant-expanded
membership geography before aggregation.

The national/authorized-scope summary and every region, target-period/season, and forecast-horizon
slice report precision, recall, F1, macro F1, PR-AUC, ROC-AUC, Brier score, ten-bin expected
calibration error, high-risk recall at probability 0.70, and useful lead time. The normal decision
threshold is 0.50. Useful lead time is the mean number of days from prediction creation to observed
event for true events detected at the normal threshold. An outcome cannot predate its prediction.

Discrimination metrics require both observed classes. A one-class slice returns `null` PR-AUC and
ROC-AUC instead of inventing a zero or perfect score. Probabilities must be finite and in `[0, 1]`.
Missing strata are not synthesized.

Production promotion requires the complete metric vocabulary plus model-card evidence for
chronological backtesting, region, season, horizon, calibration, lead time, and explicit
limitations. These are evidence-presence gates, not centrally invented acceptance thresholds;
operational threshold approval remains an institutional decision.
