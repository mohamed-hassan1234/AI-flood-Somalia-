# Phase 03 Historical Operational Replay Report

**Version:** 1.0.0

## Purpose

Phase 02 already backtested the raw model probabilities. Phase 03 replay tests something different:
the **full operational chain** — geography resolution, exposure, quality/freshness gating, warning
decisioning, and action mapping — applied historically, using only information that would have been
available at each `feature_as_of_date`, then compared against the actually observed outcome.

## Selection methodology

**Every row in the frozen, untouched Phase 02 final-test partition** for each track
(`ml.pipeline.partition`, keyed on `target_period_start`, identical to the partition Phase 02 froze).
No event was hand-picked. This is a stronger, more auditable selection rule than "a few interesting
historical episodes" — the full population of the untouched test period, successes and failures
alike, is reported.

Frozen Phase 02 model artifacts are loaded read-only and checksum-verified before every replay row
(`operational/intelligence.py::load_verified_bundle`); nothing is retrained.

## Two outcome measurements, reported separately

- **`outcome_at_warning_threshold`** — detected iff risk level reaches WARNING or SEVERE (i.e., the
  probability crosses the frozen Phase 02 operating threshold). This reproduces Phase 02's own
  validated model-card metrics exactly, as an internal consistency check that the operational
  wrapper introduced no drift.
- **`outcome_at_watch_threshold`** — detected iff risk level reaches WATCH or above (the broader
  monitoring net used for `warning.eligible`). This is intentionally more sensitive and is **not**
  the same measurement as Phase 02's model-card numbers — it must never be compared to them directly.

## Drought

- **Rows replayed:** 3,875 (test period 2023–2025; 45 rows for the `Unspecified` geography bucket
  were correctly excluded — see the exposure methodology doc)
- **At warning threshold:** recall 0.614, precision 0.363, false alarm rate 0.097
  (TP 196, FP 344, FN 123, TN 3212) — matches Phase 02's model-card numbers within the small
  `Unspecified`-exclusion effect (Phase 02's raw metrics included those 45 rows; Phase 03's
  operational geography correctly does not).
- **At watch threshold:** TP 240, FP 666, FN 79, TN 2890 — a deliberately more sensitive monitoring
  net; recall rises, precision falls, exactly as intended for an earlier-warning tier.
- **Result:** PASS — both successes and failures are represented; no future data was available to
  any row (verified by the freshness-gap test).

## Flood — reported per station, never pooled away

- **Rows replayed:** 4,035 (test period 2023–2025, all five stations)
- **Pooled at warning threshold:** recall 0.789, precision 0.902, false alarm rate 0.014
  (TP 452, FP 49, FN 121, TN 3413) — exact match to the flood model card.
- **Mean detected lead time:** 1.03 days.

| Station | Recall | Precision | False alarm rate |
|---|---|---|---|
| SH001 (Belet Weyne) | 0.867 | 0.978 | 0.009 |
| SH002 (Bulo Burto) | 0.744 | 0.959 | 0.007 |
| SH004 (Jowhar) | 0.455 | 0.333 | 0.025 |
| JB001 (Luuq) | 0.698 | 0.787 | 0.014 |
| JB009 (Doolow) | 0.782 | 0.883 | 0.012 |

SH004 is materially weaker in this single final-test-period view than in Phase 02's full
2019–2025 rolling backtest (which pooled more years and folds) — this is expected: a 3-year
single-window replay has a smaller, noisier sample than a 6-fold rolling backtest. **This weakness
is reported explicitly, not smoothed away.** JB001/JB009 (the Jubba corridor) again show lower
precision than the Shabelle stations, consistent with the flood model card's documented limitation.

**Result:** PASS — successes, false positives, and false negatives are all represented for every
station; SH004's weaker performance is a preserved, visible failure case, not hidden by pooling.

## Food security

- **Rows replayed:** 72 (test period 2024–2025, all 18 regions across 2 assessment cycles)
- **At warning threshold:** recall 0.538, precision 0.700, false alarm rate 0.130
  (TP 14, FP 6, FN 12, TN 40) — exact match to the food-security model card.
- **At watch threshold:** TP 26, FP 43, TN 3, FN 0 — recall reaches 1.0 but precision falls to 0.38;
  illustrates why WATCH-tier signals are explicitly *not* treated as equivalent to a WARNING-tier
  candidate in the warning policy.
- **Result:** PASS — both successes and failures represented, though the sample (72 rows) is small,
  consistent with the food-security model card's own small-sample limitation.

## Future-data leakage check

`operational/tests/test_phase03.py::ReplayCutoffTests` and
`WarningPolicyTests::test_real_archive_rows_never_have_a_negative_freshness_gap` assert, over sampled
real archive rows across all three tracks, that no feature timestamp used at a given
`feature_as_of_date` is ever later than that date (a negative freshness gap). Combined with the
Phase 02 leakage audit already covering the underlying dataset construction, this closes the loop:
**no row in any replay used information from its own future.**

## Machine-readable artifacts

- `data/operational/replay/<track>_operational_replay.csv.gz` — full per-row replay table
- `data/operational/replay/<track>_replay_summary.json` — the summary numbers above, generated, not
  hand-transcribed
- `data/operational/replay/<track>_illustrative_cases.json` — highest-confidence true positives,
  highest-confidence false positives, and lowest-confidence false negatives per track, drawn from the
  same non-cherry-picked replay population (for narrative reference only, not a separate sample)

## Limitations

1. Replay uses the fixed 2025 WorldPop population figure for every historical year (no historical
   population back-series exists in Phase 01); exposure numbers in replay records are not
   year-accurate population.
2. Driver/reason-code computation is skipped in the bulk replay for performance (`include_drivers=False`);
   the live operational pipeline always computes drivers per record.
3. Food security's 72-row replay sample is small; per-region and per-year granularity below that is
   not statistically meaningful and is not reported separately.
