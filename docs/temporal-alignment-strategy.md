# Phase 01 temporal alignment strategy

## Decision

The canonical agricultural early-warning calendar is the **dekad** (days 1–10,
11–20, and 21–month end). Raw observations keep their native timestamps. The
alignment layer is derived and never overwrites source data.

Flood feature engineering may additionally use a daily calendar because river
rises and extreme rainfall can occur faster than a dekad. Food-security outcomes
remain attached to their published IPC assessment/scenario periods.

## Dataset rules

| Dataset | Native time | Dekadal rule | Missing-data rule |
|---|---|---|---|
| CHIRPS v3 rainfall | Daily | Sum rainfall; retain mean/max, valid-day count, heavy-rain days and end-of-dekad dry-spell length | Never interpolate rainfall. A period is incomplete when a source day is absent. |
| MOD13Q1 V061 | 16-day composite | Assign by composite start date for reproducible baseline features. Phase 02 may use interval-weighted allocation only if the composite support interval is explicitly modeled. | Pixel QA is applied first. A district/composite with no good pixels remains null; no spatial or temporal fabrication. |
| NASA POWER GWETTOP/GWETROOT | Daily | Mean, minimum, maximum and end-of-period relative wetness | Preserve missing values; do not call these variables SMAP or volumetric soil moisture. |
| NASA POWER T2M/T2M_MAX/T2M_MIN | Daily | Mean T2M, maximum T2M_MAX, minimum T2M_MIN; derive rolling/heat indicators from daily data before or after aggregation as documented | No climatological replacement in the foundation layer. |
| River level | Observation/daily | Maximum, mean, last observation, observation count, and threshold-exceedance days per station | No forward fill across missing observations. Gaps and station-specific coverage remain explicit. |
| WFP market prices | Monthly/observation | Keep monthly grain. When used on a dekad, use only the most recent earlier published observation with its age in days; Phase 02 must set and justify a maximum age. | Never backfill from the future. Stale values are null after the chosen age limit. |
| IPC | Assessment/scenario period | Keep current, projection 1, and projection 2 distinct. Join a feature date only to the scenario period explicitly covering it. | Never forward-fill an IPC class beyond its documented validity period. |
| WorldPop | 2025 reference surface | Static exposure covariate with reference year attached | Do not interpret modeled population as a census or historical population series. |

## Baselines and leakage controls

- CHIRPS dekadal anomalies and percent-of-normal use the local 2015–2025
  archive baseline, grouped by canonical district, month, and dekad.
- MOD13Q1 NDVI/EVI anomalies use the 2015–2025 archive, grouped by canonical
  district and within-year composite number.
- For honest backtesting, Phase 02 must fit any learned normalization only on
  the training fold. The Phase 01 full-history climatologies are descriptive
  reference features, not permission to leak future outcomes.
- Scenario publication and observation availability timestamps must be honored;
  an observation cannot be used before it was available operationally.

## Model-specific calendars and overlap

| Track | Primary calendar | Common foundation window | Notes |
|---|---|---|---|
| Drought | Dekadal | 2015-01-01 through 2025-12-31 | CHIRPS, MOD13Q1, POWER wetness and temperature. |
| Flood | Daily plus dekadal summaries | 2015-01-01 through 2025-12-31 for all five gauges | Earlier station-specific experiments are possible, but the all-station window begins with JB009 in 2015. |
| Food security | Dekadal predictors; assessment-period target | 2017-01-01 through 2025-12-31 | Environmental histories, WFP markets and IPC outcomes overlap. IPC native areas remain multi-district where the geometry says so. |

The end date is the latest complete common environmental year. Data after 2025
remain useful for operational validation, but are not silently mixed into this
frozen Phase 01 backtesting window.

## Reproducibility

Acquisition/derivation commands are documented in `data/README.md`. Source URLs,
versions, local paths, reference periods, timestamps, sizes and SHA-256 checksums
are retained in the historical manifests and dataset-specific validation JSON.
