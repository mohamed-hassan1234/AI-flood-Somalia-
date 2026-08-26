# Phase 03 Warning & Action Policy

**Version:** 1.0.0

## Risk levels

Four canonical risk levels only: `NORMAL`, `WATCH`, `WARNING`, `SEVERE`. Thresholds are the frozen
Phase 02 `risk_thresholds` read directly from each track's `ml/artifacts/<track>/model_metadata.json`
— Phase 03 never redefines, recomputes, or silently changes them (verified by
`operational/tests/test_phase03.py::RiskThresholdTests`).

| Track | WATCH | WARNING | SEVERE |
|---|---|---|---|
| Drought | 0.135 | 0.27 | 0.635 |
| Flood | 0.115 | 0.23 | 0.615 |
| Food security | 0.265 | 0.53 | 0.765 |

Risk-level assignment is deterministic: it is the calibrated probability compared against these
fixed cut points inside `ml.common.ModelBundle.predict`, reused unmodified from Phase 02.

## Risk level vs. warning workflow status

These are deliberately separate fields (`operational/warning.py`):

- **Risk level** — what the model says (`NORMAL`/`WATCH`/`WARNING`/`SEVERE`).
- **Warning status** — whether that risk level is allowed to become an operational warning:
  - `NO_WARNING_RISK_NORMAL` — risk level is NORMAL; nothing to warn about.
  - `SUPPRESSED_DATA_QUALITY` — risk level is WATCH+ but critical model features are unavailable or
    outside the trained guardrail range.
  - `SUPPRESSED_STALE_DATA` — risk level is WATCH+ but a critical source is stale beyond its
    documented freshness policy.
  - `CANDIDATE` — risk level is WATCH+ and data quality/freshness are acceptable; eligible to be
    surfaced for review.

A high probability with bad or stale critical data **never** produces `CANDIDATE` — it is always
suppressed, and the underlying model probability is still preserved in the record for audit, just
not treated as actionable (`operational/tests/test_phase03.py::WarningPolicyTests`).

## Data-quality gate

Two independent quality signals are combined by taking the worse of the two
(`operational/warning.py::combined_data_quality`):

1. **Model input quality** (`GOOD`/`DEGRADED`/`INSUFFICIENT`) — reused unmodified from the frozen
   Phase 02 `ModelBundle.predict`: `INSUFFICIENT` when fewer than half of the track's three critical
   features are available; `DEGRADED` when any feature is missing or outside its 1st–99th percentile
   training range; `GOOD` otherwise.
2. **Freshness status** (`GOOD`/`DEGRADED`/`STALE_CRITICAL`) — see below.

`INSUFFICIENT` overall quality makes `probability`/`risk_level` unavailable in the prediction (the
model itself withholds them) and always suppresses warning eligibility.

## Freshness policy

Defined per track from each source's own observation cadence
(`operational/config/freshness_policy.json`) — there is no single invented global threshold:

| Track | Source | Max gap | Critical? |
|---|---|---|---|
| Drought | MOD13Q1 vegetation | 32 days (2 missed composites) | yes |
| Drought | CHIRPS rainfall | 3 days | yes |
| Drought | NASA POWER climate | 3 days | yes |
| Flood | FAO SWALIM/SNRFA gauge | 2 days | yes |
| Flood | CHIRPS rainfall | 3 days | yes |
| Flood | NASA POWER climate | 3 days | yes |
| Food security | WFP market | 120 days | no (already ~31% missing at source) |
| Food security | Previous IPC assessment | 220 days | no |
| Food security | MOD13Q1 vegetation | 32 days | yes |
| Food security | CHIRPS rainfall | 3 days | yes |
| Food security | NASA POWER climate | 3 days | yes |

Any critical column past its max gap (or missing) makes the row `STALE_CRITICAL`, which forces
overall quality to `INSUFFICIENT` and suppresses warning eligibility with `SUPPRESSED_STALE_DATA`.
A stale non-critical column only degrades quality to `DEGRADED`, which does not by itself block a
warning.

## Warning reason codes

Structured, evidence-backed codes only — never free text as the source of truth
(`operational/drivers.py::REASON_CODE_MAP`). A code is only attached when the corresponding feature
both ranks among the top local drivers (median-perturbation attribution) **and** moves the
prediction in the direction the code describes:

`LOW_NDVI_ANOMALY`, `HIGH_VEGETATION_STRESS_RISK`, `PERSISTENT_RAINFALL_DEFICIT`,
`SOIL_MOISTURE_DEFICIT`, `ELEVATED_TEMPERATURE_STRESS`, `LOW_VEGETATION_DATA_COVERAGE`,
`RIVER_LEVEL_NEAR_THRESHOLD`, `RAPID_RIVER_RISE`, `HEAVY_ANTECEDENT_RAINFALL`,
`SATURATED_ANTECEDENT_SOIL`, `MARKET_PRICE_STRESS`, `IPC_DETERIORATION_SIGNAL`,
`POPULATION_CONTEXT`.

## Recommended-action catalogue

Fixed, versioned, machine-readable (`operational/config/action_catalog.json`, version 1.0.0) —
24 actions across 3 tracks × 3 severities (WATCH/WARNING/SEVERE; NORMAL gets none). No action text
is generated dynamically by a model or LLM; `operational/actions.py::recommended_actions` is a pure
lookup keyed on `(risk_type, risk_level)`.

Every action carries:

- `action_id`, `action_category`, `action_text`, `intended_actor`, `time_horizon`, `prerequisites`,
  `source_reference`, `priority`, `scope_notes`
- `status`: `SUGGESTED` (routine monitoring/assessment) or `REQUIRES_REVIEW` (anything touching
  notification of authorities, public communication, evacuation-route review, or SEVERE-level
  escalation) — **never `APPROVED`**. Phase 03 does not pretend an authority approved an action.
- `why_triggered`: `{risk_type, risk_level, reason_codes}` for traceability.

No action text orders an evacuation or states that food has been distributed — both are explicitly
tested (`ActionCatalogueTests.test_no_action_text_orders_an_evacuation`). High-impact public actions
(river-basin authority notification, evacuation-route review, public communication) are marked
`REQUIRES_REVIEW` at every severity where they appear, preserving human decision authority per the
project's human-in-the-loop requirement.

## Human review requirement

Phase 03 implements only the `CANDIDATE` stage of the eventual review workflow
(model → intelligence → candidate warning → analyst review → approval → publication → follow-up →
outcome). No approval, publication, or notification is performed by this code. Every
`REQUIRES_REVIEW` action and every `CANDIDATE` warning status is a proposal for Phase 04's future
governed workflow to act on, not an executed action.
