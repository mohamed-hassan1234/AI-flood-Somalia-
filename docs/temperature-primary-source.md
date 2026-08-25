# Temperature primary-source decision

Status: accepted for Phase 01  
Decision date: 2026-08-25  
Scope: Somalia drought, heat-stress, evapotranspiration-context, and food-security features

## Decision

Use **NASA POWER daily 2 m air temperature** as the production historical
temperature source. The retained variables are `T2M`, `T2M_MAX`, and
`T2M_MIN`, in degrees Celsius and UTC days. The local production window is
2000-01-01 through 2025-12-31, the latest full calendar year selected for this
Phase 01 archive.

NASA POWER derives its meteorological parameters from NASA GMAO MERRA-2 and
appends GEOS low-latency data near real time. The native meteorological grid is
0.5 degrees latitude by 0.625 degrees longitude. The official daily service is
available from 1981 to near real time and defines daily maxima and minima from
the underlying hourly values.

Authoritative references:

- [NASA POWER meteorological methodology](https://power.larc.nasa.gov/docs/methodology/meteorology/)
- [NASA POWER daily API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/)
- [NASA POWER temporal processing](https://power.larc.nasa.gov/docs/methodology/data/processing/)
- [NASA POWER meteorological assessment](https://power.larc.nasa.gov/docs/methodology/meteorology/assessment/)

## Candidate comparison

| Candidate | Spatial resolution | Temporal resolution and history | Access and storage | Decision |
|---|---:|---|---|---|
| NASA POWER / MERRA-2 | Native 0.5 x 0.625 degrees | Daily, 1981 to near real time | Public API; small point time series; no account | **Primary** |
| MOD11A1 V061 | Approximately 1 km | Daily land-surface temperature, MODIS era | Many tiled QA rasters; cloud-dependent observations | Secondary diagnostic |
| ERA5-Land | 0.1 degrees distributed; about 9 km native | Hourly, 1950 to present | Strong land reanalysis, but the configured CDS path requires an API key that is absent locally | Future upgrade candidate |

MOD11A1 measures land-surface skin temperature rather than 2 m air
temperature. It can add spatial heat diagnostics, but it is not interchangeable
with `T2M` and would introduce cloud/QA gaps and substantially more tiled data.
The existing MOD11A1 sample remains a secondary validation asset.

ERA5-Land is scientifically strong and finer than POWER. It was not selected
for this completion pass because no `.cdsapirc` or `cdsapi` installation is
configured, while the public POWER service supplies an immediately reproducible
multi-decadal record from the same reanalysis family used for antecedent
wetness. See the [Copernicus ERA5-Land dataset](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land?tab=overview).

## Local implementation

- Connector: `data/scripts/phase01_power_history.py`
- Immutable raw responses: `data/raw/climate/nasa_power_merra2/`
- District-to-source-cell mapping: `data/metadata/nasa_power_district_grid_mapping.csv`
- Daily output: `data/processed/climate/nasa_power_district_daily_20000101_20251231.csv.gz`
- Dekadal output: `data/processed/climate/nasa_power_district_dekadal_20000101_20251231.csv.gz`
- Validation: `data/metadata/nasa_power_history_validation.json`
- Manifest: `data/metadata/nasa_power_history_manifest.json`

The connector makes one request per unique source cell nearest to the official
reference point of each district. Seventy-two unique cells serve 91 districts,
so duplicate provider requests are avoided. The mapping is explicit and must
not be described as polygon-area averaging.

The validated archive contains 864,227 district-day rows and 85,176
district-dekad rows. All 9,497 expected days are present for all three
temperature variables. The observed ranges are:

- `T2M`: 12.00 to 37.76 degrees Celsius
- `T2M_MAX`: 19.39 to 45.15 degrees Celsius
- `T2M_MIN`: 4.86 to 32.26 degrees Celsius

Dekadal mean-temperature anomalies use a documented 2001-2020
month-by-dekad baseline. Daily observations are not fabricated or forward-filled.

## Consequences

- The archive is long, internally aligned, compact, and reproducible without
  interactive authentication.
- It is appropriate for district-scale historical covariates, not neighborhood
  heat mapping.
- Coarse cells can be shared by neighboring districts. Downstream evaluation
  must account for this spatial dependence.
- POWER near-real-time GEOS values may later be superseded by improved
  climate-quality MERRA-2 values; refreshes must retain source/API version and
  checksums.
- MOD11A1 can remain optional. Its absence from the full historical feature
  table does not block Phase 02.

