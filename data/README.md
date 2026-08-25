# Phase 01 data foundation

Original files already present in this directory are treated as immutable source evidence. They
remain at their existing paths to avoid breaking manual provenance or application references.

New Phase 01 work uses these directories:

- `raw/`: newly acquired, immutable source files grouped by dataset family;
- `staging/`: reversible source-specific normalization;
- `processed/`: validated canonical tables and geospatial derivatives;
- `features/`: reserved for Phase 02 feature construction; Phase 01 does not train models;
- `metadata/`: inventories, registries, matrices, crosswalks, checksums, and validation reports;
- `scripts/`: reproducible audit, acquisition, and preparation utilities.

Run the non-destructive inventory from the repository root:

```shell
python data/scripts/phase01_audit.py
```

The script writes `metadata/file_inventory.csv` and `metadata/validation_report.json`. It never
modifies source files.

Re-run the public Phase 01 connectors with:

```shell
python data/scripts/phase01_connectors.py chirps --start 1981-01-01 --end 1981-01-31 --max-files 31
python data/scripts/phase01_connectors.py market
python data/scripts/phase01_connectors.py ipc
python data/scripts/phase01_connectors.py population
python data/scripts/phase01_connectors.py nasa-power --start 20250101 --end 20251231
python data/scripts/phase01_connectors.py modis vegetation --start 2026-07-01 --end 2026-07-31 --max-items 1
python data/scripts/phase01_connectors.py modis temperature --start 2020-07-01 --end 2020-07-02 --max-items 1
python data/scripts/phase01_power_history.py auth-audit
python data/scripts/phase01_power_history.py all --start 20000101 --end 20251231 --workers 4
python data/scripts/phase01_history.py chirps --start 2015-01-01 --end 2025-12-31 --workers 8
python data/scripts/phase01_history.py modis --start 2015-01-01 --end 2025-12-31 --workers 8
python data/scripts/phase01_validate.py
python data/scripts/validate_river_station_metadata.py
python data/scripts/validate_boundary_provenance.py
python data/scripts/ipc_geographic_mapping.py
python data/scripts/phase01_readiness.py
```

The MODIS commands intentionally default to a bounded sample. Increase `--max-items` or change the
date range only after estimating storage requirements. NASA Earthdata remains the authoritative
producer; the connector uses Microsoft Planetary Computer's hosted V061 COG assets and preserves
the source STAC records and NASA DOI links. The CHIRPS command downloads the final ERA5-disaggregated
(`rnl`) daily product and refuses a range larger than `--max-files` until the storage limit is
explicitly increased.

`phase01_history.py` is the production historical path. CHIRPS uses the official compact final
`rnl/p25` daily files, calculates district daily, dekadal, monthly, and climatological-season
features, and writes yearly resume checkpoints instead of retaining thousands of global rasters.
MOD13Q1 writes per-composite and yearly resume checkpoints and reads only Somalia-intersecting
V061 COG tiles through aligned approximately 1 km overviews; NDVI, EVI, VI Quality, and pixel
reliability remain on the same sampling grid and the documented pixel QA mask is applied before
district summaries. Source asset URLs, item IDs, archive periods and output checksums are retained.

`phase01_power_history.py` deduplicates the 91 official district reference points to 72 native
NASA POWER/MERRA-2 cells before requesting `T2M`, `T2M_MAX`, `T2M_MIN`, `GWETTOP`, and
`GWETROOT`. It preserves immutable provider JSON, writes a checksum manifest, and derives daily and
dekadal gzip CSV tables. `GWETTOP` and `GWETROOT` are relative modeled wetness indices; they are not
renamed or represented as SMAP volumetric soil moisture. See `../docs/temperature-primary-source.md`
and `../docs/soil-moisture-primary-source.md` for the source decisions and scientific limits.

`phase01_validate.py` never edits raw files. It rebuilds the canonical boundary copies, river,
market, IPC, population, MODIS-statistics outputs, source registry, availability matrix, temporal
matrix, overlap assessment, geographic crosswalk, and consolidated validation report. See
`../docs/phase-01-data-foundation-report.md` for the interpreted result and known blockers.

`validate_river_station_metadata.py` independently checks that all river observations have station
metadata, thresholds are ordered, and official gauge points are compared with canonical district
polygons. It preserves the documented JB009 border-area exception rather than moving the source
coordinate.

`validate_boundary_provenance.py` checks all ADM0-ADM2 features for the embedded `v03` version and
2025-01-08 valid-on date used in the documented OCHA COD-AB metadata match.

`phase01_validate.py` now calls the IPC geography generator after rebuilding its base crosswalk, so
the measured IPC polygon relationships and coordinate-based WFP market relationships persist on
every normal validation run. IPC point features remain explicitly non-areal and the WFP source
`admin2=Banadir` value remains quarantined rather than overwritten.

`phase01_readiness.py` is the final machine-readable acceptance gate. It writes
`metadata/phase01_readiness.json`, prints readiness for drought, flood, and food-security tracks,
and exits nonzero while a genuine required input is incomplete.
