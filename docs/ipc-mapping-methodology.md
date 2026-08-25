# IPC geographic mapping methodology

## Decision

IPC analysis areas are **not Somalia districts**. The supplied IPC GeoJSON contains both genuine
areal features and point features. Polygon/MultiPolygon features are related to districts through
measured spatial overlap. Point features for urban and IDP entries are retained as reference points
and are never converted into district outcome labels.

The mapping is usable for exposure/aggregation design, but it is not permission to duplicate one IPC
classification into every intersecting district. Phase 02 target construction must define a weighting
and population-at-risk method separately.

## Inputs and observed semantics

- IPC spatial source: `data/raw/food_security/ipc_som.geojson`.
- IPC historical table: `data/raw/food_security/ipc_som_area_long.csv`.
- Canonical districts: `data/processed/boundaries/som_admin2_canonical.geojson`.
- IPC snapshot analysis ID(s): 87143416.
- Geometry inventory: 26 Polygon, 18 MultiPolygon,
  63 Point features.
- Exact-title candidate snapshot period(s): Apr 2026 (2026-04-01 to 2026-06-30; 107/107 totals and 472/535 phase values match), Jan 2026 (2026-01-01 to 2026-01-31; 107/107 totals and 236/535 phase values match).

The best-supported period is **Apr 2026**
(2026-04-01 to 2026-06-30), selected by the highest exact
phase-value signature match. This is a reproducible inference because the CSV does not expose the
GeoJSON `anl_id` as a join key; it is not represented as an explicit provider ID join.

The `admin_type` property distinguishes `polygon`, `urb`, and `idp`. Urban/IDP point coordinates are
cartographic/reference locations; a point has no area, so `intersection_area`,
`district_overlap_pct`, and `ipc_area_overlap_pct` are intentionally blank for those records.

## Polygon overlay procedure

1. Read IPC and canonical district geometries in EPSG:4326.
2. Validate each geometry. Invalid geometries are repaired only in memory for overlay, never written
   back to raw data. Repair counts are recorded in the JSON report.
3. Reproject both layers to World Equidistant Cylindrical / NSIDC EASE-Grid 2.0 Global
   (EPSG:6933), an equal-area CRS.
4. Intersect every IPC polygon with every canonical district having a positive-area intersection.
5. Calculate:
   - `intersection_area` = intersection area / 1,000,000, with `intersection_area_unit=km2`;
   - `district_overlap_pct` = intersection area / canonical district area × 100;
   - `ipc_area_overlap_pct` = intersection area / IPC area × 100.
6. Preserve overlaps below 0.01% as `boundary_sliver_preserved`, but mark them
   ineligible for areal weighting. They are not silently discarded.
7. Mark an IPC polygon ambiguous for single-district labeling when it has more than one substantive
   district intersection or its summed canonical coverage is outside 99–101%.

## Mapping types

- `polygon_overlap_single_district`: one substantive district and complete canonical coverage.
- `polygon_overlap_multi_district`: the IPC analysis area legitimately spans districts.
- `polygon_partial_single_district`: only one substantive district but incomplete canonical coverage.
- `boundary_sliver_preserved`: positive overlay below the documented threshold.
- `reference_point_within_district_not_area_mapping`: point container only; not a target mapping.
- `reference_point_outside_canonical_districts`: no point container; quarantined.

## Temporal limitation

The GeoJSON is a single snapshot, while the area CSV is historical. Exact matching of the current
GeoJSON titles to the CSV identifies candidate assessment dates, but does not establish that IPC area
boundaries were unchanged in earlier analyses. Apply this overlay directly to the represented snapshot.
Historical reuse requires versioned IPC geometry or explicit confirmation that an area's definition
was stable. Name equality alone is insufficient.

## Phase 02 implications

- Keep `aar_id`/IPC area title and validity period as the native outcome geography.
- For polygon features, district exposure may use documented overlap weights, preferably combined
  with population weighting rather than area weighting alone.
- Do not copy a multi-district IPC phase to every intersecting district as independent labels.
- Do not use urban/IDP anchor-point containment as a district label.
- Do not forward-fill IPC labels beyond the published validity period.

## WFP Banadir finding

HDX's authoritative package metadata describes the WFP resource as a market registry and tags its
columns with Humanitarian Exchange Language. The value `Banadir` is explicitly supplied in
`#adm2+name`, but in affected rows it duplicates `admin1=Banadir`; the canonical layer has Banadir as
a region with constituent districts, not a district named Banadir. The metadata does not explain why
this incompatible convention was used, so it is not relabeled by name.

Safe handling:

- preserve `admin2=Banadir` unchanged;
- quarantine it from name-based district transformations;
- spatially relate each market point to a canonical district as a separate relationship;
- never overwrite the provider field with the point-derived district.

Observed affected price rows: 1944. Registry markets: 10.
Point-resolved markets: 10. Quarantined points: 0.

Authoritative metadata provenance is preserved in `data/metadata/hdx_market_package.json`; it records
WFP as the organization, Registry as the methodology, market coordinates, HXL `#adm1+name` and
`#adm2+name` semantics, and the CC BY-IGO licence.

## Outputs

- `data/processed/food_security/ipc_geographic_mapping.csv`
- `data/processed/food_security/ipc_geographic_mapping.json`
- `data/processed/market_prices/wfp_banadir_geographic_resolution.csv`
- `data/metadata/geographic_crosswalk.csv`
