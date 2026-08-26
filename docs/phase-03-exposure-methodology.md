# Phase 03 Exposure Methodology

**Version:** 1.0.0

This document explains exactly what "exposure" means in Phase 03, where the numbers come from, and
— just as importantly — where they honestly stop.

## Population source

All population figures trace to the Phase 01 WorldPop-derived summaries:

- `data/processed/population/district_population_2025.csv` (91 canonical districts)
- `data/processed/population/region_population_2025.csv` (18 canonical regions)

**Population year: 2025. Source: WorldPop-derived modeled population, not census enumeration.**
WorldPop is a gridded population model, not a ground count; district/region totals inherit that
model's uncertainty. No new population source was downloaded for Phase 03 — the existing Phase 01
foundation was used as-is (`operational/geography.py::GeographyRegistry`).

## Aggregation

District and region totals are read directly from the Phase 01 summary tables — no re-aggregation
from raster was performed in Phase 03. `operational/geography.py` loads both tables once per process
and exposes typed `District`/`Region`/`Station` lookups that raise `UnsupportedGeographyError` for
any id outside the validated Phase 02 model scope (including the `Unspecified` bucket — see below).

## Drought exposure

- **Method:** the district's full 2025 WorldPop population is reported as `population_context`
  always, and as `population_potentially_exposed` only when the district's risk level is WATCH or
  above (0.0 at NORMAL).
- **Why the whole district:** the drought target (`agricultural_vegetation_stress_next_composite`)
  is itself a district-level signal — Phase 01 does not contain a validated cropland or settlement
  mask that would support a finer exposure geometry. Reporting a sub-district number would fabricate
  precision the data does not support.
- **What it is not:** `population_potentially_exposed` is a whole-district approximation of who
  *could* be in an area under environmental stress, not a count of people confirmed affected by
  drought impact. See `docs/models/drought-model-card.md` for the underlying model's own scope.

## Regional exposure (food security)

- **Method:** the region's total population is reported as `population_context`.
  `population_potentially_exposed` is always `null` for every risk level.
- **Why null:** the food-security target predicts a **binary** threshold — whether the observed
  regional Crisis-or-worse population share will reach 20% — not the exact share. Multiplying region
  population by an assumed percentage (e.g., "always report 20%") would fabricate a specific
  humanitarian-impact number the model does not produce. A future track could estimate an ordinal or
  continuous burden and revisit this; Phase 03 does not.
- **Historical context only:** `operational/exposure.py::observed_historical_population_in_phase3plus`
  computes a population-in-Phase-3+ figure from the previously **observed** IPC Phase 3+ percentage
  for replay/backtest narratives only. It is never attached to a live prediction record, and it is
  clearly distinct from a model output.

## Flood exposure — the critical case

**No floodplain, river-corridor, or historical inundation footprint exists anywhere in the Phase 01
data foundation.** The Phase 02 flood model predicts a gauge-level threshold exceedance, not an
inundation polygon. Therefore:

- `population_potentially_exposed` is **always `null`** for flood, at every risk level, unconditionally.
- `population_context` reports the population of the district nearest the gauge (from
  `river_station_metadata_validation.json` / the `canonical_district_id` already resolved inside the
  Phase 02 flood dataset), for **operational orientation only** — so an analyst knows roughly which
  district the gauge sits in, not how many people would be inundated.
- No buffer radius around a gauge was invented. No city population was substituted for exposed
  population. This is a deliberate, tested behavior
  (`operational/tests/test_phase03.py::ExposureSemanticTests`), not a gap that was overlooked.

| Station | Linked district | 2025 population context |
|---|---|---|
| SH001 | SO2001 — Belet Weyne | see `data/processed/population/district_population_2025.csv` |
| SH002 | SO2002 — Bulo Burto | " |
| SH004 | SO2101 — Jowhar | " |
| JB001 | SO2606 — Luuq | " |
| JB009 | SO2605 — Doolow | " |

## Potential exposure vs. affected population

Every exposure record distinguishes:

- `population_context` — always known, always the relevant geography's total population.
- `population_potentially_exposed` — populated only where a defensible exposure geometry exists
  (drought district, at WATCH+); `null` everywhere a defensible geometry does not exist (flood,
  food security).

Neither field is ever labeled `affected_population` or `confirmed_affected`. No Phase 03 code path
produces a "confirmed affected" number — that would require independent field verification or
inundation data this project does not have. This distinction is enforced by an automated test
(`ExposureSemanticTests.test_no_field_anywhere_claims_confirmed_affected_population`).

## The `Unspecified` district exclusion

One row in the Phase 01 district population table (`canonical_district_id == "Unspecified"`,
region SO22/Banadir) is a residual bucket for observations that could not be resolved to a specific
Banadir sub-district. It carries a population figure but is not a real, mappable place. Phase 03
explicitly rejects it (`GeographyRegistry.district()` raises `UnsupportedGeographyError`) rather than
emitting a warning for a district a responder could never locate. This affects roughly 1.1% of
historical drought observations, all excluded from operational output with a documented,
non-silent reason (`skipped_unsupported_geography` in every pipeline/replay run summary).

## Known limitations

- WorldPop is a model, not a census; treat all population figures as estimates.
- Drought's whole-district exposure figure overstates precision below the district level.
- Flood and food-security `population_potentially_exposed` being `null` is expected, permanent
  behavior under the current data foundation, not a bug to "fix" by inventing a number.
- Population year is fixed at 2025 for the whole historical archive; no year-specific historical
  population back-series was available in Phase 01, so replay records over 2015–2025 use the same
  2025 population figure. This is a documented simplification, not a claim of year-accurate
  historical population.
