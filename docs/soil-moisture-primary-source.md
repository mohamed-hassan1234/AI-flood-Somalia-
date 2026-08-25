# Soil moisture and antecedent-wetness source decision

Status: accepted substitution for Phase 01  
Decision date: 2026-08-25  
Scope: drought and flood antecedent-wetness features

## Decision

Use **NASA POWER `GWETTOP` and `GWETROOT`** as the primary historical
antecedent-wetness variables for model development. POWER reports both as
unitless relative soil-wetness indices:

- `GWETTOP`: surface soil wetness
- `GWETROOT`: root-zone soil wetness

These variables come from the NASA GMAO MERRA-2/GEOS meteorological system.
They are not SMAP measurements and are never renamed `soil_moisture` in the
processed schema. SMAP SPL3SMP_E V006 remains a higher-resolution,
observation-based secondary source for validation and future operational
features.

Authoritative references:

- [NASA POWER meteorological methodology](https://power.larc.nasa.gov/docs/methodology/meteorology/)
- [NASA POWER data sources](https://power.larc.nasa.gov/docs/methodology/data/sources/)
- [NASA POWER parameter dictionary](https://power.larc.nasa.gov/parameters/)
- [NSIDC SMAP data catalogue](https://nsidc.org/data/smap/data)
- [SPL3SMP_E V006 user guide](https://nsidc.org/sites/default/files/documents/user-guide/spl3smp_e-v006-userguide.pdf)

## Why historical SMAP is not the primary archive

The local SPL3SMP_E V006 sample covers 2026-07-01 through 2026-07-31. The
product itself is daily, approximately 9 km, and available from 2015-03-31.
However, the local credential audit found:

- no `.netrc` or `_netrc`;
- no Earthdata token-related environment-variable name;
- no `earthaccess` installation or persisted Earthdata session;
- an existing legacy download script that requires an interactive password and
  contains no stored password; and
- no supported unattended mechanism that can be tested without asking for a
  credential.

The machine-readable audit is
`data/metadata/earthdata_auth_audit.json`. It records only mechanism presence
and environment-variable names; it never records secret values.

This is an access blocker, not a scientific rejection of SMAP. SMAP retains
value for satellite validation and for the 2015-present operational period once
a supported Earthdata token is provisioned outside source control.

## Alternatives considered

| Candidate | Resolution/history | Strength | Constraint | Decision |
|---|---|---|---|---|
| SMAP SPL3SMP_E V006 | Daily, 9 km, 2015-present | Observation-based surface volumetric soil moisture with QA | Earthdata authentication unavailable locally; shorter history | Secondary |
| ERA5-Land soil water | Hourly, about 9 km native, 1950-present | Four soil layers and long consistent reanalysis | CDS API key absent locally; hourly volume larger | Future upgrade candidate |
| POWER MERRA-2/GEOS wetness | Daily, 0.5 x 0.625 degrees, 1981-NRT | Public, compact, surface and root-zone wetness, aligned with temperature | Coarser and modeled; relative index rather than volumetric water content | **Primary antecedent-wetness substitute** |

ERA5-Land remains a scientifically valid upgrade if a CDS credential is later
provisioned. It must be introduced under its own variable names and compared
against the established POWER/SMAP series rather than silently replacing them.

## Local implementation and validation

- Connector: `data/scripts/phase01_power_history.py`
- Immutable raw responses: `data/raw/climate/nasa_power_merra2/`
- Daily output: `data/processed/climate/nasa_power_district_daily_20000101_20251231.csv.gz`
- Dekadal output: `data/processed/climate/nasa_power_district_dekadal_20000101_20251231.csv.gz`
- District/grid mapping: `data/metadata/nasa_power_district_grid_mapping.csv`
- Download manifest: `data/metadata/nasa_power_history_manifest.json`
- Validation report: `data/metadata/nasa_power_history_validation.json`

Coverage is 2000-01-01 through 2025-12-31: 9,497 continuous days, 91
districts, 72 unique source cells, 864,227 district-day rows, and zero missing
`GWETTOP` or `GWETROOT` values. Provider-reported units are `1`. Validated
ranges are 0.07-1.00 for surface wetness and 0.20-1.00 for root-zone wetness.

The dekadal product averages the real daily values within each calendar dekad.
No daily values are interpolated and no missing observations are forward-filled.

## Scientific consequences

- These variables support historical antecedent-wetness and drought-state
  features; they are not ground truth for volumetric soil water.
- The coarse source grid cannot resolve sub-district hydrology or riverbank
  saturation. River observations and rainfall remain necessary for flood work.
- District values are nearest-cell samples, not area-weighted polygon means.
- SMAP comparisons should be performed only on dates with accepted retrieval QA
  and should account for the resolution and variable-definition mismatch.
- Model documentation must identify `GWETTOP`/`GWETROOT` as reanalysis wetness
  indices and keep SMAP provenance separate.

