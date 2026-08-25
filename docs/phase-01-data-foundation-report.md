# Phase 01 — Real Data Foundation Report

**System:** Somalia AI Food Security, Drought & Flood Early Warning Platform  
**Validation date:** 25 August 2026  
**Scope:** data foundation only; no model training or production alerting

## Executive decision

**PHASE 01 STATUS: PARTIAL — NOT READY FOR PHASE 02 MODEL TRAINING.**

The repository now has a reproducible, validated Phase 01 data layer with real authoritative data,
checksums, source metadata, canonical boundaries, geographic crosswalks, processed tables, zonal
population totals, and acquisition scripts. The four previously missing families—temperature,
food-security outcomes, market prices, and population—are represented by real local files and were
validated.

Phase 01 cannot honestly be called complete because the local environmental history is still only a
sample: CHIRPS has one January 1981 dekad plus 38 days in 2026; MOD13Q1 has one 16-day tile; SMAP has July
2026; and MOD11A1 has one daily tile. These files prove formats and pipelines but are not a training
archive. Authoritative FAO SWALIM/SNRFA coordinates and current operational thresholds are now
linked to all five river histories; their effective-from dates are not published.

## 1. How the data system works

```text
Authoritative provider
    -> idempotent connector or preserved manual export
    -> immutable raw/source file
    -> structural and scientific validation
    -> canonical geography crosswalk
    -> processed Phase 01 table/raster statistics
    -> source registry + availability/temporal matrices
    -> Phase 02 governed snapshot (future work)
```

The application remains responsible for governed operational ingestion. Phase 01 prepares source
evidence and canonical derivatives; it does not silently load data into the operational database,
publish warnings, calculate official IPC classifications, or train models.

### Directory contract

| Layer | Purpose |
|---|---|
| `data/` existing top-level files | Manually collected originals retained at their original paths for compatibility. |
| `data/raw/` | Newly downloaded immutable provider files. |
| `data/staging/` | Temporary/recoverable work. The canceled legacy WorldPop transfer is explicitly quarantined here as `.partial`. |
| `data/processed/` | Reproducible canonical tables, boundary copies, raster statistics, and zonal summaries. |
| `data/features/` | Reserved for Phase 02; no model features were fabricated in Phase 01. |
| `data/metadata/` | Checksums, inventory, source registry, availability matrix, temporal matrix, crosswalk, STAC records, and validation reports. |
| `data/scripts/` | Reproducible audit, connector, and validation programs. |

## 2. Step-by-step reproducible workflow

Run from the repository root:

```shell
python data/scripts/phase01_audit.py
python data/scripts/phase01_connectors.py chirps --start 1981-01-01 --end 1981-01-31 --max-files 31
python data/scripts/phase01_connectors.py market
python data/scripts/phase01_connectors.py ipc
python data/scripts/phase01_connectors.py population
python data/scripts/phase01_connectors.py nasa-power --start 20250101 --end 20251231
python data/scripts/phase01_connectors.py modis vegetation --start 2026-07-01 --end 2026-07-31 --max-items 1
python data/scripts/phase01_connectors.py modis temperature --start 2020-07-01 --end 2020-07-02 --max-items 1
python data/scripts/phase01_validate.py
python data/scripts/phase01_audit.py
```

The public connectors are retry-safe and idempotent. Downloads are written to a `.part` file,
renamed only after a successful non-empty response, and recorded with the source URL, byte size,
SHA-256 digest, timestamp, and disposition in `data/metadata/download_manifest.json`. Credentials
are not hard-coded. MODIS sample limits and date ranges are configurable; NASA POWER requests are
automatically tiled to provider-compatible regional extents.

## 3. Dataset-by-dataset result

### 01 — Somalia administrative boundaries

- **Status:** COMPLETE for structural Phase 01 use and source metadata.
- **Source:** OCHA Somalia, *Somalia - Subnational Administrative Boundaries (COD-AB)*, distributed
  through HDX; the project-supplied files were retained unchanged.
- **Coverage:** 18 regions and 91 district features.
- **CRS:** GeoJSON WGS84/EPSG:4326 semantics.
- **Validation:** all admin1/admin2 files readable; zero invalid geometries; source PCodes retained.
- **Canonical outputs:** `data/processed/boundaries/som_admin1_canonical.geojson` and
  `som_admin2_canonical.geojson`.
- **Version/terms:** embedded `v03`, valid on 2025-01-08; CC BY IGO. The original local download
  date was not recorded, so the filesystem modification date is not misrepresented as that date.

### 02 — Historical rainfall

- **Status:** PARTIAL.
- **Source:** UCSB Climate Hazards Center CHIRPS v3.
- **Provider coverage:** 1981 to near-present, daily 0.05-degree data.
- **Actual local coverage:** one historical dekadal raster (`1981-01`, dekad 1) plus 38 continuous
  `rnl` daily files from 2026-06-24 through 2026-07-31. The dekadal raster is not misrepresented as
  a daily observation.
- **Format/units:** GeoTIFF; precipitation in mm/day; WGS84 geographic grid.
- **Validation:** 39/39 rasters readable; no duplicate daily dates.
- **Limitation:** not a local historical archive and therefore insufficient for multi-year anomaly
  baselines or model training.
- **Official sources:** [CHIRPS v3 description](https://www.chc.ucsb.edu/data/chirps3) and
  [bulk repository](https://data.chc.ucsb.edu/products/CHIRPS/v3.0/).

### 03 — Vegetation / NDVI / EVI

- **Status:** PARTIAL.
- **Source:** NASA LP DAAC MOD13Q1 V061, obtained as NASA-produced COG assets hosted by Microsoft
  Planetary Computer.
- **Provider coverage:** 2000 to present; 16-day; 250 m MODIS sinusoidal tiles.
- **Actual local coverage:** one Terra tile for the 2026-07-12 to 2026-07-27 composite.
- **Variables:** NDVI, EVI, VI Quality, and pixel reliability.
- **Scaling:** NDVI/EVI encoded values multiplied by `0.0001`; raw and QA assets remain immutable.
- **Observed pixel-reliability codes:** 0, 1, and 3 in the validation tile.
- **Limitation:** one tile is not complete Somalia coverage or a historical archive.
- **Official source:** [NASA DOI](https://doi.org/10.5067/MODIS/MOD13Q1.061).

### 04 — Soil moisture

- **Status:** PARTIAL.
- **Source:** NASA NSIDC `SPL3SMP_E` V006.
- **Provider coverage:** 2015-03-31 to present; daily; 9 km EASE-Grid 2.0.
- **Actual local coverage:** 31 dates, 2026-07-01 through 2026-07-31; 38 subset granules.
- **Variables:** AM soil moisture, latitude/longitude, and retrieval quality flags.
- **Units/fill:** cubic centimetres per cubic centimetre; source fill `-9999` retained.
- **Validation:** all HDF5/netCDF4 files readable and science/quality arrays inspected. Dates with
  multiple granules are listed in the validation report and are not discarded as duplicates.
- **Limitation:** July 2026 only; authenticated historical Earthdata acquisition is not automated.
- **Official source:** [NSIDC SPL3SMP_E V006](https://nsidc.org/data/spl3smp_e/versions/6).

### 05 — River levels / hydrology

- **Status:** COMPLETE for the five supplied gauge histories, with operational limitations.
- **Source:** FAO SWALIM/SNRFA CSV exports.
- **Stations:** SH001 Belet Weyne, SH002 Bulo Burti/Bulo Burto, SH004 Jowhar, JB001 Luuq, and JB009
  Dollow/Doolow.
- **Rows:** 87,848 total.
- **Coverage:** station-dependent, from as early as 1951-01-01; all five extend to 2026-08-25.
- **Validation:** dates parse; station codes match case-insensitively; no negative levels; missing
  water levels and gaps remain explicit. JB001 contains two rows participating in one exact
  date/station/level duplicate pair.
- **Canonical output:** `data/processed/river_levels/river_levels_canonical.csv`.
- **Station metadata:** authoritative coordinates, operational status, and current moderate-risk,
  high-risk, and bankfull levels are stored in `data/processed/river_station_metadata.csv` and
  `.json`. The provider does not publish threshold effective-from dates.
- **Spatial exception:** the official JB009 point is 1.252 km outside the canonical Doolow polygon;
  it is retained unchanged and is not reassigned. Missing water levels are not filled or treated as
  zero.
- **Official system:** [FAO SWALIM flood and river monitoring](https://frrims.faoswalim.org/).

### 06 — Temperature / land-surface temperature

- **Status:** PARTIAL.
- **Primary source:** NASA LP DAAC MOD11A1 V061.
- **Primary local sample:** one Terra daily tile for 2020-07-01 with `LST_Day_1km`, `QC_Day`,
  `LST_Night_1km`, and `QC_Night`.
- **Correct conversion:** `Celsius = encoded value × 0.02 - 273.15`; encoded fill/values below the
  documented valid minimum are excluded. QC mandatory bits are preserved and inspected.
- **Secondary source:** NASA POWER/MERRA-2 2 m air temperature, explicitly not treated as LST.
- **Secondary local coverage:** daily 2025 `T2M`, `T2M_MAX`, and `T2M_MIN`, 540 unique grid points,
  591,300 rows, zero missing/fill values across the four tiled Somalia-bounding-box files per
  variable.
- **Limitation:** MOD11A1 remains a one-tile sample, so historical LST anomalies cannot be trained.
- **Official sources:** [MOD11A1 DOI](https://doi.org/10.5067/MODIS/MOD11A1.061) and
  [NASA POWER daily API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/).

### 07 — Food security / IPC outcomes

- **Status:** COMPLETE WITH REVIEW FLAGS for historical outcome use at national/admin1/IPC-area
  resolution; not district labels.
- **Source:** IPC machine-readable Somalia country package via HDX.
- **Coverage:** 2017-01-01 through 2026-06-30.
- **Rows:** 76,077 across national, level-1, and IPC analysis-area tables.
- **Variables:** analysis date, validity dates, current/first projection/second projection, phase,
  persons, and percentage.
- **Critical distinction:** `current`, `first projection`, and `second projection` remain explicit in
  `assessment_period_type`; projections are not recoded as observations.
- **Quality finding:** the national file has three exact duplicate rows; they remain reported and are
  not silently deleted. Phases include 1–5, `3+`, and `all` aggregate rows.
- **Canonical output:** `data/processed/food_security/ipc_outcomes_canonical.csv`.
- **Limitation:** IPC analysis areas/livelihood areas must not be asserted as districts without a
  validated spatial crosswalk.
- **Source package:** [HDX Somalia IPC data](https://data.humdata.org/dataset/somalia-acute-food-insecurity-country-data).

### 08 — Market / food prices

- **Status:** COMPLETE WITH GEOGRAPHIC REVIEW.
- **Source:** WFP Somalia food prices via HDX.
- **Coverage:** 1995-01-15 through 2026-06-15.
- **Rows:** 42,231; 47 markets; 22 commodities.
- **Variables:** date, admin1/admin2, market and coordinates, commodity, source unit, price type,
  currency, local price, and USD price.
- **Units/currencies:** `Head`, `KG`, `L`, `USD/LCU`, and `Unit`; SOS and SLS. These remain explicit
  and are never combined as if interchangeable.
- **Validation:** no invalid dates, missing prices, non-positive prices, or duplicate business keys.
- **Geographic review:** the WFP `admin2=Banadir` value is intentionally unresolved because the
  canonical reference contains individual Banadir districts, not a district named Banadir.
- **Canonical output:** `data/processed/market_prices/wfp_food_prices_canonical.csv`.
- **Source package:** [WFP Somalia food prices on HDX](https://data.humdata.org/dataset/wfp-food-prices-for-somalia).

### 09 — Population / exposure

- **Status:** COMPLETE WITH METHODOLOGY LIMITATIONS.
- **Source:** WorldPop Somalia 2025 constrained population R2025A v1.
- **Coverage/resolution:** Somalia; 3 arc-second, approximately 100 m; EPSG:4326; persons per pixel.
- **Raster:** 12,509 × 16,381 pixels; NoData `-99999`.
- **Validation:** raster readable and intersects every canonical district; no district has zero
  valid raster pixels.
- **Derived outputs:** 91 district totals and 18 region totals. The summed district estimate is
  19,139,579.592 persons. Density is calculated using WGS84 geodesic polygon area.
- **Limitations:** modeled alpha estimate, not a census; boundary mismatch can alter border-cell
  allocation. Preserve the release/version with every exposure result.
- **Official source/terms:** [WorldPop DOI](https://doi.org/10.5258/SOTON/WP00839), CC BY 4.0.

## 4. Geographic standardization

The project-supplied boundaries remain canonical. Existing source PCodes are used as stable IDs:
18 admin1 codes and 91 admin2 features. Source spellings are preserved in the crosswalk and mapped
only by normalized exact match or a documented unambiguous alias.

Examples include `Dollow -> Doolow`, `Bulo Burti -> Bulo Burto`, `Juba Dhexe -> Middle Juba`, and
`Shabelle Hoose -> Lower Shabelle`. Confidence and match method are stored. The only unresolved
value is WFP's district-level `Banadir`; it is flagged for review rather than guessed.

## 5. Data-quality summary

| Check | Result |
|---|---|
| Source files inventoried | 115 |
| Source bytes | 1,001,843,780 |
| Zero-byte files | 0 |
| Structurally unreadable files | 0 |
| Suspected partial files in source paths | 0 |
| Exact duplicate files by SHA-256 | 0 groups |
| Boundary invalid geometries | 0 |
| Geographic crosswalk unresolved | 1 (`WFP admin2=Banadir`) |
| Explicit quarantined transfer | one canceled legacy WorldPop 2020 `.partial` in `data/staging/failed_downloads/`; excluded from raw and processing |
| Excluded connector trial | one valid but overlapping first-pass NASA POWER tile remains immutable in raw and is explicitly excluded from canonical processing; the 12 coordinate-labelled files are the accepted set |

The full field-level results are in `data/metadata/phase01_validation_report.json`. The lower-level
file inventory is in `data/metadata/file_inventory.csv` and `data/metadata/validation_report.json`.

## 6. Production-source decisions

| Family | Selected production source | Acquisition decision |
|---|---|---|
| Boundaries | OCHA Somalia COD-AB v03 | Keep the matched project copy; source valid-on date and CC BY IGO terms are recorded without replacing files. |
| Rainfall | CHIRPS v3 | Public bulk HTTPS connector supports guarded date ranges; execute the full historical synchronization before training. |
| Vegetation | NASA MOD13Q1 V061 | Direct Earthdata is authoritative; current reproducible sample connector uses NASA-produced V061 COG mirror and preserves STAC provenance. |
| Soil moisture | NASA SPL3SMP_E V006 | Earthdata-authenticated; current files remain manual until credentials are configured securely. |
| River levels | FAO SWALIM/SNRFA | Manual exports retained; connector/API status requires provider agreement. |
| LST | NASA MOD11A1 V061 | Same governed STAC sample strategy as MOD13Q1; expand by tile/date before training. |
| Air temperature | NASA POWER/MERRA-2 | Secondary/fallback covariate only; never silently substituted for LST. |
| Food security | IPC via HDX | Automated fixed-resource connector; validity-period types remain distinct. |
| Markets | WFP via HDX | Automated fixed-resource connector; preserve units/currencies and provider IDs. |
| Population | WorldPop R2025A v1 | Automated annual reference grid; carry alpha/model/version disclaimer. |

Connector classification:

- **Automated:** CHIRPS final daily `rnl`, MOD13Q1/MOD11A1 bounded STAC, NASA POWER, IPC/HDX,
  WFP/HDX, and WorldPop.
- **Semi-automated:** none.
- **Manual:** project boundaries and FAO SWALIM/SNRFA exports.
- **Blocked:** historical SMAP automation is `BLOCKED_INTERACTIVE_AUTH`; direct NASA Earthdata
  requires a valid user token. The minimal action is to configure that token in the runtime
  environment or approved credential store, never in the script or repository.

## 7. Temporal overlap and Phase 02 readiness

The only three-source environmental integration window in local files is 2026-07-12 through
2026-07-27 for CHIRPS `rnl` daily rainfall, one MOD13Q1 tile, and SMAP. That is suitable only for
pipeline integration testing.

| Future model | Readiness | Reason |
|---|---|---|
| Drought | BLOCKED | No multi-year local overlap across CHIRPS, MOD13Q1, SMAP, and temperature for anomaly construction and temporal validation. |
| Flood | BLOCKED | River histories and official station metadata exist, but rainfall/SMAP local overlap is only July 2026. |
| Food security | BLOCKED | IPC and market histories are useful, but environmental predictors are not locally historical and IPC analysis areas are not district labels. |

This does not block Phase 02 software design or ingestion-pipeline engineering. It blocks honest
model training, backtesting, and production-readiness claims.

## 8. How Phase 02 should consume the foundation

1. Freeze a versioned source manifest with hashes from `download_manifest.json` and
   `file_inventory.csv`.
2. Select one boundary revision and use canonical PCodes for all joins.
3. Expand environmental archives before defining the training window.
4. Decode source scale/fill/QA before aggregation. Do not aggregate encoded MODIS values.
5. Preserve `assessment_period_type` and train observed/current IPC labels separately from
   projections.
6. Keep market unit, currency, commodity, grade, and price type in the feature key; normalize only
   through an explicit, versioned method.
7. Use population reference year/version in exposure lineage; do not treat the grid as ground truth.
8. Construct time-aware, geography-aware snapshots with no future leakage.
9. Report missingness and coverage; never turn missing observations into zero.
10. Do not start model training until the blocked historical windows have been acquired and rerun
    through `phase01_validate.py`.

## 9. Artifacts

Core metadata:

- `data/metadata/source_registry.csv` and `.json`
- `data/metadata/data_availability_matrix.csv`
- `data/metadata/temporal_coverage_matrix.csv`
- `data/metadata/temporal_overlap_report.json`
- `data/metadata/geographic_crosswalk.csv`
- `data/metadata/phase01_validation_report.json`
- `data/metadata/download_manifest.json`
- `data/metadata/file_inventory.csv`

Processed data:

- canonical admin1/admin2 GeoJSON;
- canonical combined river-level CSV;
- canonical WFP price CSV;
- canonical IPC outcome CSV;
- WorldPop district and region population CSVs;
- MOD13Q1 and MOD11A1 decoded sample-statistics CSVs.

## Final decision

**PHASE 01 NOT COMPLETE.**

The genuine blockers preventing Phase 02 model training are:

1. incomplete multi-year local CHIRPS, MOD13Q1, SMAP, and MOD11A1 archives;
2. no validated district interpretation for IPC analysis-area outcomes.

All other identified quality issues are documented and preserved rather than hidden.
