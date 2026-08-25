# River-station and boundary metadata evidence

**Evidence review date:** 25 August 2026  
**Scope:** FAO SWALIM/SNRFA metadata for five project gauges and provenance enrichment for the existing Somalia boundary archive

## River stations

The authoritative [SNRFA station catalogue](https://snrfa.faoswalim.org/stations/) publishes station
identity, river, operational status, altitude, coordinate values, and selected catchment properties.
The authoritative [FRRIMS river-level table](https://frrims.faoswalim.org/rivers/levels?mapsubid=20&subid=17)
publishes current moderate-risk, high-risk, and bankfull levels.

| Code | Station | River | Latitude | Longitude | Moderate (m) | High (m) | Bankfull (m) | Status |
|---|---|---|---:|---:|---:|---:|---:|---|
| SH001 | Belet Weyne | Shabelle | 4.735980 | 45.205960 | 6.50 | 7.30 | 8.30 | Functional |
| SH002 | Bulo Burti | Shabelle | 3.857020 | 45.567270 | 6.50 | 7.20 | 8.00 | Functional |
| SH004 | Jowhar | Shabelle | 2.778720 | 45.504860 | 5.00 | 5.25 | 5.50 | Functional |
| JB001 | Luuq | Juba | 3.791720 | 42.542640 | 5.50 | 6.00 | 7.00 | Functional |
| JB009 | Dollow | Juba | 4.187770 | 42.079382 | 4.50 | 5.00 | 6.00 | Functional |

The station catalogue's displayed column headings are inconsistent with its values: it labels the
42-45 degree column as latitude and the 2-4 degree column as longitude. The same official station
page embeds a Leaflet `location` array in valid `[latitude, longitude]` order. The processed metadata
uses the map order and records the source anomaly rather than silently hiding it.

The reviewed official pages do not publish threshold effective-from dates or threshold revision
history. Those fields remain null. Catchment area is published for SH001 (207,000 km²), SH002
(231,000 km²), and JB001 (166,000 km²); it was not published for SH004 or JB009 and is not inferred.

All 87,848 existing river observations use one of the five metadata codes. Four source points fall
inside their canonical project district polygons: Belet Weyne (SO2001), Bulo Burto (SO2002), Jowhar
(SO2101), and Luuq (SO2606). The authoritative JB009 point does not intersect the project Doolow
polygon. This border-area discrepancy is retained as a spatial exception; the station coordinate is
not moved and the station is not reassigned to manufacture a polygon match.

Machine-readable outputs:

- `data/processed/river_station_metadata.csv`
- `data/processed/river_station_metadata.json`

## Boundary provenance

The existing archive matches OCHA Somalia's [Somalia Subnational Administrative Boundaries
(COD-AB)](https://data.humdata.org/dataset/cod-ab-som). Evidence includes the same 18 ADM1 and 91
ADM2 features, PCodes, operational-zone layers, embedded `valid_on=2025-01-08`, and embedded
`version=v03`. HDX distributes the dataset under CC BY IGO; provider metadata says it was reviewed
in December 2024 and data was last updated on 15 January 2025.

The local archive uses OGC CRS84, equivalent to WGS 84 longitude-latitude axis semantics used as
EPSG:4326 by the project. It was not replaced. Its original download transaction was not recorded,
so the download date remains unknown; the 25 August 2026 filesystem modification date is retained
only as local evidence and is not relabelled as a download date.

Machine-readable evidence: `data/metadata/boundary_provenance.json`.
