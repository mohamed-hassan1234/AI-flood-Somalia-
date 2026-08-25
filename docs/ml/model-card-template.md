# Model card: [model and version]

## Intended use

- Risk domain and target:
- Forecast horizon:
- Geography and season coverage:
- Human decision supported:
- Explicitly prohibited uses:

## Data and lineage

- Dataset snapshot hash:
- Feature version:
- Source and boundary versions:
- Missingness and exclusions:
- Leakage controls:

## Evaluation

- Chronological backtest periods:
- Precision, recall, F1, macro F1, PR-AUC, ROC-AUC, Brier score, and high-risk recall:
- Ten-bin expected calibration error and useful lead time (days):
- Performance by region, season, and horizon:
- Benchmark comparison and promotion rationale:

## Limitations and safeguards

- Low-data and out-of-distribution behavior:
- Main explanations/drivers:
- Known bias and uncertainty:
- Monitoring and rollback criteria:

PR-AUC and ROC-AUC must be recorded as unavailable, not zero, when an evaluation slice contains
only one observed class. Useful lead time includes only true observed events detected at the
decision threshold and must never use an outcome timestamp earlier than its prediction.

Model output is not an official IPC/FSNAU classification and cannot publish a warning.
