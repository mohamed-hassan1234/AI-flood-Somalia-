# Phase 01 — Real Data Foundation Completion Report

**System:** Somalia AI Food Security, Drought and Flood Early Warning Platform

**Validated:** 26 August 2026

**Scope:** Phase 01 data foundation only; no model training, prediction, warning publication, or Phase 02 implementation

## Executive decision

**PHASE 01 STATUS: COMPLETE — READY FOR PHASE 02.**

All Phase 01 acceptance gates pass. The drought, flood, and food-security data tracks each have a
verified local training window, canonical geography, source lineage, processed outputs, integrity
checks, and a documented temporal-alignment method. The final readiness report contains no genuine
blockers.

This decision means that governed Phase 02 feature engineering and model development may begin. It
does not mean that a model has been trained or approved, that the application database automatically
ingests these files, or that the system can issue an official IPC classification or operational
warning.

## 1. How the system gets and processes data

```text
Authoritative provider or preserved provider export
    -> retry-safe connector / immutable source archive
    -> atomic checkpoint plus URL, version, date, size, and SHA-256 lineage
    -> structural, temporal, spatial, scientific, fill-value, and QA validation
    -> canonical OCHA region/district geography and documented crosswalk
    -> district-level daily, dekadal, monthly, seasonal, or assessment-period tables
    -> source registry, manifests, availability matrix, temporal matrix, overlap report
    -> independent Phase 01 readiness gate
    -> governed Phase 02 snapshot and feature construction (future work)
```

Step by step:

1. Preserve originals in `data/` or `data/raw/`; never overwrite a provider field with a guessed
   canonical value.
2. Download public archives with bounded parallelism, retry/backoff, `.part`/atomic rename, and
   recoverable annual or period checkpoints.
3. Validate file readability, checksums, date coverage, duplicate keys, CRS/georeferencing,
   scientific ranges, source fill values, and QA masks.
4. Resolve geography against OCHA COD-AB v03. Keep source labels, matching method, confidence, and
   review status in the crosswalk.
5. Produce canonical district series while retaining missing observations as null—not zero—and
   retaining IPC assessment-period semantics, market units/currencies, and river station identity.
6. Register each source and output in manifests and coverage matrices.
7. Run the independent readiness program. Phase 01 is complete only when every model track and every
   acceptance check pass.

The operational application and this research data foundation are deliberately separate. Nothing in
Phase 01 silently inserts rows into the application database, trains a model, publishes an alert, or
sends a notification.

## 2. Storage and reproducibility contract

| Location | Responsibility |
|---|---|
| `data/raw/` | Immutable provider downloads and machine-readable source packages. |
| `data/staging/` | Recoverable work and explicitly excluded transfer artifacts. |
| `data/processed/` | Canonical boundaries and reproducible district/area derivatives. |
| `data/features/` | Reserved for Phase 02; no features or labels were fabricated here. |
| `data/metadata/` | Inventories, hashes, manifests, crosswalks, matrices, lineage, and validation/readiness reports. |
| `data/scripts/` | Acquisition, mapping, validation, audit, and readiness programs. |
| `docs/` | Source-selection, mapping, temporal-alignment, system, and completion documentation. |

Reproduction from the repository root uses the project environment:

```shell
.venv\Scripts\python.exe data\scripts\phase01_history.py chirps --start 2015-01-01 --end 2025-12-31 --workers 7
.venv\Scripts\python.exe data\scripts\phase01_history.py modis --start 2015-01-01 --end 2025-12-31 --workers 7
.venv\Scripts\python.exe data\scripts\phase01_power_history.py
.venv\Scripts\python.exe data\scripts\validate_river_station_metadata.py
.venv\Scripts\python.exe data\scripts\validate_boundary_provenance.py
.venv\Scripts\python.exe data\scripts\ipc_geographic_mapping.py
.venv\Scripts\python.exe data\scripts\phase01_validate.py
.venv\Scripts\python.exe data\scripts\phase01_audit.py
.venv\Scripts\python.exe data\scripts\phase01_readiness.py
```

The archive builders are resumable. CHIRPS is checkpointed annually; MODIS is checkpointed by
composite and year. Successful checkpoints are reused after their schema, district/date uniqueness,
QA rule, and source-item identities are verified.

## 3. Completed datasets and where they came from

### Administrative boundaries

- **Status:** COMPLETE.
- **Source:** OCHA Somalia COD-AB v03 via HDX; embedded valid-on date 2025-01-08; CC BY IGO.
- **Coverage:** 1 country, 18 regions, 91 district features in CRS84/EPSG:4326 semantics.
- **Method:** the supplied local files remain unchanged; their unknown original download date is not
  replaced with a filesystem timestamp.
- **Outputs:** `data/processed/boundaries/som_admin1_canonical.geojson` and
  `som_admin2_canonical.geojson`.

### Rainfall

- **Status:** COMPLETE.
- **Source:** UCSB Climate Hazards Center CHIRPS v3 final `rnl` p25 daily GeoTIFFs.
- **Window:** 2015-01-01 through 2025-12-31; all 4,018 days.
- **Outputs:** 365,638 district-day rows, 36,036 district-dekads, 12,012 district-months, and
  4,004 district-seasons for 91 districts.
- **Quality:** zero missing dates, zero missing district-days, zero negative rainfall rows; minimum
  valid-pixel fraction 0.5.
- **Important resolution statement:** this compact production archive uses the official 0.25-degree
  p25 distribution, not the native 0.05-degree CHIRPS grid.

### Vegetation (NDVI/EVI)

- **Status:** COMPLETE WITH EXPLICIT SOURCE GAPS AND STRICT-QA NULLS.
- **Source:** NASA LP DAAC MOD13Q1 V061 Terra assets, hosted as NASA-produced COGs by Microsoft
  Planetary Computer.
- **Window:** 2015-01-01 through 2025-12-31; 242 of 253 nominal 16-day composite starts (95.65%).
- **Scale/QA:** encoded NDVI/EVI × 0.0001; accept `pixel_reliability=0`, MODLAND QA bits 0–1 equal
  zero, and raw VI range -2000..10000. Fill and masked values remain null.
- **Processing:** native 231.656 m MODIS sinusoidal tiles are sampled through an aligned
  nearest-neighbour 4× COG overview (approximately 1 km) for district summaries.
- **Outputs:** 22,022 district-period rows with NDVI/EVI mean, median, baseline, anomaly, anomaly-z,
  vegetation stress, counts, fractions, and QA summary.
- **Missingness:** 15.01% archive-wide, concentrated in very small urban Banadir polygons; 0.71%
  outside Banadir. Banadir is 73.03% null under strict QA. No spatial or temporal values are imputed.
- **Provider gaps:** 2023-02-18; 2024-08-12 and 2024-12-18; and 2025-07-12 through 2025-11-01 at
  16-day starts. Data resume on 2025-11-17, 2025-12-03, and 2025-12-19.

The collector specifically guards against four discovered failure modes: STAC result truncation,
out-of-range temporal intersections, missing optional `platform` metadata, and duplicate production
timestamps. It selects Terra from the immutable `MOD13Q1.` product prefix, queries 31-day windows,
filters start dates strictly, and retains only the newest logical granule. A signed-int8/source-fill
metadata conflict is handled with a promoted dtype and explicit mask, without changing valid QA
codes.

### Temperature and antecedent wetness

- **Status:** COMPLETE as the selected historical primary source.
- **Source:** NASA POWER Release 10 MERRA-2/GEOS meteorology.
- **Window:** 2000-01-01 through 2025-12-31; all 9,497 days.
- **Variables:** T2M, T2M_MAX, T2M_MIN in °C; GWETTOP and GWETROOT as unitless modeled relative
  wetness.
- **Coverage:** 91 districts mapped to 72 unique native source cells; 864,227 daily and 85,176
  dekadal rows; zero missing parameter values.
- **Resolution:** 0.5° latitude × 0.625° longitude; nearest source cell to each district reference
  point, not a polygon mean.
- **Scientific identity:** GWETTOP/GWETROOT are an antecedent-wetness equivalent, never labeled as
  SMAP or volumetric soil moisture. MOD11A1 and local SMAP subsets remain optional diagnostics.

### River levels

- **Status:** COMPLETE for the five supplied gauges.
- **Source:** FAO SWALIM/SNRFA observations and official station metadata.
- **Stations/rows:** SH001, SH002, SH004, JB001, JB009; 87,848 observations.
- **Thresholds (moderate/high/bankfull metres):** SH001 6.5/7.3/8.3; SH002 6.5/7.2/8.0;
  SH004 5.0/5.25/5.5; JB001 5.5/6.0/7.0; JB009 4.5/5.0/6.0.
- **Validation:** coordinates, station identities, source hosts, and threshold ordering pass.
- **Exception:** official JB009 is 1,252.181 m outside the canonical Doolow polygon. It is retained
  unchanged and documented, not moved. Provider threshold effective dates/revision history are not
  published. One exact JB001 observation pair remains reported.

### IPC food-security outcomes

- **Status:** COMPLETE WITH DOCUMENTED GEOGRAPHIC AMBIGUITY.
- **Source:** IPC Somalia machine-readable package via HDX; historical outcomes start in 2017.
- **Mapping:** 107 snapshot features produce 362 mapping rows: 44 polygons/multipolygons are
  inherently multi-district; 63 urban/IDP point features receive containment relationships only.
- **Quality:** all six mapping validation checks pass. Polygon coverage averages 99.5896% and has a
  91.8817% minimum; 213 substantive overlaps and 86 boundary slivers remain explicit.
- **Semantics:** current and projection periods are never mixed; IPC polygons use overlap weights;
  urban/IDP reference points are not treated as area footprints or district labels.
- **Snapshot limitation:** title/population/phase signatures best support April 2026 current validity,
  but do not prove that historical IPC geometry was stable or provide a direct analysis-ID join.

### Market prices

- **Status:** READY WITH REVIEW CONTROLS.
- **Source:** WFP Somalia food-price package via HDX.
- **Banadir control:** 1,944 price rows retain provider `admin2=Banadir`; that value is quarantined
  from canonical district matching. Ten registry markets are independently point-resolved from
  coordinates to canonical district IDs. The original provider field is never overwritten.
- **Semantics:** commodity, unit, currency, grade, and price type remain part of the observation key.

### Population/exposure

- **Status:** COMPLETE WITH MODEL LIMITATIONS.
- **Source:** WorldPop Somalia 2025 constrained population R2025A v1, approximately 100 m,
  EPSG:4326, persons per pixel.
- **Coverage:** all 91 districts and 18 regions; no district lacks valid raster pixels. District
  estimates sum to 19,139,579.797 persons.
- **Limitation:** this is an alpha modeled allocation, not a census; boundary mismatch affects
  border-cell allocation.

## 4. Canonical geography and temporal alignment

OCHA COD-AB source PCodes are the canonical IDs. The 218-row crosswalk preserves source spelling,
canonical match, method, confidence, and review requirement. Aliases such as Dollow/Doolow and Bulo
Burti/Bulo Burto are explicit. The one unresolved crosswalk item is the safely quarantined WFP
`admin2=Banadir` label; its market points have a separate validated relationship.

The common analysis calendar is described in `docs/temporal-alignment-strategy.md`:

| Model track | Verified window | Calendar and inputs | Readiness |
|---|---|---|---|
| Drought | 2015-01-01–2025-12-31 | 396 dekads; CHIRPS, MOD13Q1 composites, POWER temperature/wetness | READY |
| Flood | 2015-01-01–2025-12-31 | 4,018 daily days plus 396 dekads; CHIRPS, five gauges, POWER | READY |
| Food security | 2017-01-01–2025-12-31 | 324 predictor dekads joined only to native IPC assessment targets | READY |

Alignment must be backward-looking and leakage-safe. A 16-day MODIS composite is available only
after its support interval; IPC projections remain projections; future observations must never enter
an earlier feature snapshot.

## 5. Validation and acceptance results

| Gate | Result |
|---|---|
| Python compilation for Phase 01 scripts | PASS |
| Boundary structure and provenance | PASS (1/18/91) |
| CHIRPS continuity and district coverage | PASS |
| MOD13Q1 inventory, QA, coverage, and checksum | PASS |
| POWER temperature/wetness continuity | PASS |
| River coordinates, thresholds, identity, observations | PASS |
| IPC geometry interpretation | PASS WITH DOCUMENTED AMBIGUITY |
| WFP Banadir quarantine and point mapping | PASS |
| Population validation | PASS |
| Registry, matrices, manifests, and 218-row crosswalk | PASS |
| Source integrity audit | PASS |
| Drought / flood / food-security readiness | READY / READY / READY |

The final source audit inventoried 188 source files totaling 1,058,333,819 bytes. It found zero
zero-byte files, suspected partial downloads, unreadable files, or exact duplicate file groups.

The legacy/sample validators intentionally still describe local SMAP and MOD11A1 coverage as
partial. They are secondary diagnostics and are not the selected Phase 01 historical primary source;
NASA POWER provides the complete temperature and antecedent-wetness history.

## 6. Key files produced

Historical data:

- `data/processed/rainfall/chirps_v3_daily_district_2015-01-01_2025-12-31.csv`
- `data/processed/rainfall/chirps_v3_dekad_district_2015-01-01_2025-12-31.csv`
- `data/processed/rainfall/chirps_v3_monthly_district_2015-01-01_2025-12-31.csv`
- `data/processed/rainfall/chirps_v3_seasonal_district_2015-01-01_2025-12-31.csv`
- `data/processed/vegetation/mod13q1_v061_district_2015-01-01_2025-12-31.csv`
- `data/processed/climate/nasa_power_district_daily_20000101_20251231.csv.gz`
- `data/processed/climate/nasa_power_district_dekadal_20000101_20251231.csv.gz`
- `data/processed/river_levels/river_levels_canonical.csv`
- `data/processed/food_security/ipc_geographic_mapping.csv`
- `data/processed/market_prices/wfp_banadir_geographic_resolution.csv`

Governance and evidence:

- `data/metadata/phase01_readiness.json`
- `data/metadata/phase01_completion_report.json`
- `data/metadata/phase01_validation_report.json`
- `data/metadata/validation_report.json`
- `data/metadata/historical_archive_manifest.csv`
- `data/metadata/nasa_power_history_manifest.json`
- `data/metadata/source_registry.csv` and `.json`
- `data/metadata/data_availability_matrix.csv`
- `data/metadata/temporal_coverage_matrix.csv`
- `data/metadata/temporal_overlap_report.json`
- `data/metadata/geographic_crosswalk.csv`
- `data/metadata/chirps_historical_validation.json`
- `data/metadata/mod13q1_historical_validation.json`
- `data/metadata/nasa_power_history_validation.json`

Documentation:

- `docs/system-documentation-report.md`
- `docs/temporal-alignment-strategy.md`
- `docs/ipc-mapping-methodology.md`
- `docs/river-station-and-boundary-metadata.md`
- `docs/temperature-primary-source.md`
- `docs/soil-moisture-primary-source.md`

## 7. Scientific limits and external blockers

There are **no external blockers preventing Phase 02**. Optional historical SMAP automation remains
unavailable without NASA Earthdata authentication, but SMAP is a secondary diagnostic and is not
required because the selected POWER wetness-equivalent archive is complete.

Known limits that Phase 02 must carry forward:

- CHIRPS p25 is a 0.25-degree compact product; small districts can share source cells, and the local
  2015–2025 climatology is 11 years rather than a WMO 30-year normal.
- MODIS native resolution is 250 m, but these district statistics sample the aligned approximately
  1 km overview. Provider date gaps and strict-QA nulls are not interpolated.
- POWER is coarse and point-sampled. GWETTOP/GWETROOT are modeled relative wetness, not measured
  volumetric soil moisture.
- River thresholds lack published effective dates; the JB009 location exception must remain in
  lineage.
- IPC areas are not districts; multi-district weights and point-only relationships must be honored.
- WFP units/currencies are not interchangeable; the Banadir label must remain quarantined.
- WorldPop is a modeled exposure surface, not census truth.
- Phase 01 establishes data readiness only. Model skill, calibration, fairness, operational
  thresholds, human approval, and alert governance must be demonstrated in later phases.

## Final decision

**PHASE 01 COMPLETE — READY FOR PHASE 02.**

Machine-readable evidence: `data/metadata/phase01_readiness.json` reports `COMPLETE`, all three model
tracks report `READY`, and `genuine_blockers` is empty. Phase 02 work was not started as part of this
completion.
