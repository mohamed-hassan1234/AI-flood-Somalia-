# Governed geospatial analysis

Boundary analysis uses approved, versioned `Polygon` or `MultiPolygon` GeoJSON. Imports reject
empty or topologically invalid geometry before persistence. Each `(administrative unit, version)`
revision is immutable; subsequent imports retain prior geometry, effective dates, source, and
parent linkage while the administrative-unit table remains a latest-version projection. Passing
`boundary_version` to `GET /api/v1/geography/boundaries` retrieves an authorized historical vector
layer. All analytical endpoints require
`geography.read` and reuse membership geography; an inaccessible unit is returned as not found.

## Point-to-district mapping

`GET /api/v1/geography/resolve-point` accepts bounded longitude/latitude values plus optional
`boundary_version` and `reference_date`. It considers only accessible district boundaries valid on
that date. No match returns 404. More than one match returns 409 instead of silently assigning a
point across overlapping or shared governed boundaries. The response includes the stable unit ID,
stable code, hierarchy, validity, source, and boundary version.

## Bounded raster-grid zonal statistics

`POST /api/v1/geography/admin-units/{id}/zonal-statistics` accepts a north-to-south rectangular
grid and its WGS84 extent. Requests are bounded to 512 rows and 512 columns. Cell centers are
tested against the stored unit polygon and the response reports:

- cells in the zone;
- valid and missing cell counts;
- valid-cell coverage;
- minimum, maximum, and arithmetic mean;
- administrative-unit ID and boundary version.

`null` raster cells remain missing and are excluded from numeric summaries. A zone with no valid
cells returns null statistics, never a fabricated zero. This JSON-grid interface is the governed
calculation boundary used by file/provider adapters; production Cloud-Optimized GeoTIFF decoding,
reprojection, and resampling must occur in a separately bounded ingestion worker before calling
the calculation.
