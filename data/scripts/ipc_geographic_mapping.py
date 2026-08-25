"""Build a defensible IPC-area to canonical-district spatial relationship table.

The IPC export mixes areal Polygon/MultiPolygon features with Point features used
for urban and IDP analysis entries.  Only areal features receive overlap areas and
percentages.  Point features are retained as reference-point observations and are
never promoted to district labels.

Raw source files are read-only.  Outputs are replaced atomically.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform


DATA = Path(__file__).resolve().parents[1]
PROJECT = DATA.parent
IPC_PATH = DATA / "raw" / "food_security" / "ipc_som.geojson"
IPC_AREA_CSV = DATA / "raw" / "food_security" / "ipc_som_area_long.csv"
DISTRICT_PATH = DATA / "processed" / "boundaries" / "som_admin2_canonical.geojson"
WFP_PRICE_PATH = DATA / "raw" / "market_prices" / "wfp_food_prices_som.csv"
WFP_MARKET_PATH = DATA / "raw" / "market_prices" / "wfp_markets_som.csv"
OUTPUT_DIR = DATA / "processed" / "food_security"
CSV_OUTPUT = OUTPUT_DIR / "ipc_geographic_mapping.csv"
JSON_OUTPUT = OUTPUT_DIR / "ipc_geographic_mapping.json"
BANADIR_OUTPUT = DATA / "processed" / "market_prices" / "wfp_banadir_geographic_resolution.csv"
METHOD_PATH = PROJECT / "docs" / "ipc-mapping-methodology.md"
NOW = datetime.now(timezone.utc).isoformat()

EQUAL_AREA_CRS = "EPSG:6933"
MIN_SUBSTANTIVE_IPC_PERCENT = 0.01

MAPPING_COLUMNS = [
    "ipc_area_id",
    "analysis_id",
    "ipc_period",
    "ipc_area_title",
    "ipc_admin_type",
    "ipc_geometry_type",
    "district_id",
    "district_name",
    "district_region_id",
    "district_region_name",
    "intersection_area",
    "intersection_area_unit",
    "district_overlap_pct",
    "ipc_area_overlap_pct",
    "mapping_type",
    "ambiguous",
    "eligible_for_areal_weighting",
    "notes",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    part.replace(path)


def atomic_csv(path: Path, rows: Iterable[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    with part.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    part.replace(path)


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_text(text.rstrip() + "\n", encoding="utf-8")
    part.replace(path)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def repaired_geometry(geometry: dict[str, Any]) -> tuple[Any, bool]:
    geom = shape(geometry)
    if geom.is_valid:
        return geom, False
    # buffer(0) is used only for intersection computation; raw geometry is never
    # edited.  The repair count is surfaced in the JSON report.
    repaired = geom.buffer(0)
    if repaired.is_empty or not repaired.is_valid:
        raise ValueError("Geometry is invalid and could not be repaired for overlay")
    return repaired, True


def infer_snapshot_periods(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank candidate CSV periods using title and published total-population matches."""
    feature_population: dict[str, int | None] = {}
    feature_phases: dict[str, dict[str, int | None]] = {}
    for feature in features:
        props = feature.get("properties", {})
        try:
            population = int(float(props.get("estimated_population")))
        except (TypeError, ValueError):
            population = None
        title = str(props.get("title", ""))
        feature_population[title] = population
        feature_phases[title] = {}
        for phase in ("1", "2", "3", "4", "5"):
            try:
                feature_phases[title][phase] = int(float(props.get(f"phase{phase}_population")))
            except (TypeError, ValueError):
                feature_phases[title][phase] = None

    matches: dict[tuple[str, str, str, str], dict[str, int]] = defaultdict(
        lambda: {"title_match_count": 0, "population_match_count": 0, "phase_value_match_count": 0, "phase_value_comparison_count": 0}
    )
    with IPC_AREA_CSV.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            title = str(row.get("Area", ""))
            if title not in feature_population or str(row.get("Validity period", "")).lower() != "current":
                continue
            key = (row.get("Date of analysis", ""), row.get("Validity period", ""), row.get("From", ""), row.get("To", ""))
            try:
                csv_population = int(float(row.get("Number", "")))
            except (TypeError, ValueError):
                csv_population = None
            phase = str(row.get("Phase", "")).lower()
            if phase == "all":
                matches[key]["title_match_count"] += 1
                if csv_population is not None and csv_population == feature_population[title]:
                    matches[key]["population_match_count"] += 1
            elif phase in {"1", "2", "3", "4", "5"} and csv_population is not None:
                expected = feature_phases[title][phase]
                if expected is not None:
                    matches[key]["phase_value_comparison_count"] += 1
                    if csv_population == expected:
                        matches[key]["phase_value_match_count"] += 1
    candidates = [
        {
            "date_of_analysis": analysis,
            "validity_period": validity,
            "from": start,
            "to": end,
            **counts,
            "geojson_feature_count": len(features),
        }
        for (analysis, validity, start, end), counts in matches.items()
    ]
    return sorted(
        candidates,
        key=lambda item: (-item["phase_value_match_count"], -item["population_match_count"], -item["title_match_count"], item["from"]),
    )


def build_ipc_mapping() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ipc = load_json(IPC_PATH)
    districts_fc = load_json(DISTRICT_PATH)
    to_equal_area = Transformer.from_crs("EPSG:4326", EQUAL_AREA_CRS, always_xy=True).transform

    districts: list[dict[str, Any]] = []
    repaired_districts = 0
    for feature in districts_fc.get("features", []):
        geom, repaired = repaired_geometry(feature["geometry"])
        repaired_districts += int(repaired)
        props = feature.get("properties", {})
        equal_area = transform(to_equal_area, geom)
        districts.append({"geometry": geom, "equal_area": equal_area, "area_km2": equal_area.area / 1_000_000, "properties": props})

    rows: list[dict[str, Any]] = []
    geometry_counts: Counter[str] = Counter()
    admin_type_counts: Counter[str] = Counter()
    repaired_ipc = 0
    polygon_summaries: list[dict[str, Any]] = []
    point_match_counts: Counter[str] = Counter()

    for feature in ipc.get("features", []):
        props = feature.get("properties", {})
        area_id = str(props.get("aar_id", ""))
        analysis_id = str(props.get("anl_id", ""))
        ipc_period = str(props.get("ipc_period", ""))
        title = str(props.get("title", ""))
        admin_type = str(props.get("admin_type", ""))
        geom, repaired = repaired_geometry(feature["geometry"])
        repaired_ipc += int(repaired)
        geom_type = geom.geom_type
        geometry_counts[geom_type] += 1
        admin_type_counts[admin_type] += 1

        common = {
            "ipc_area_id": area_id,
            "analysis_id": analysis_id,
            "ipc_period": ipc_period,
            "ipc_area_title": title,
            "ipc_admin_type": admin_type,
            "ipc_geometry_type": geom_type,
        }

        if geom_type in {"Point", "MultiPoint"}:
            matches = [district for district in districts if district["geometry"].covers(geom)]
            point_match_counts[str(len(matches))] += 1
            if not matches:
                rows.append({
                    **common,
                    "district_id": "",
                    "district_name": "",
                    "district_region_id": "",
                    "district_region_name": "",
                    "intersection_area": "",
                    "intersection_area_unit": "",
                    "district_overlap_pct": "",
                    "ipc_area_overlap_pct": "",
                    "mapping_type": "reference_point_outside_canonical_districts",
                    "ambiguous": True,
                    "eligible_for_areal_weighting": False,
                    "notes": "IPC urban/IDP point is a display or reference location, not an analysis-area footprint.",
                })
            else:
                for district in matches:
                    district_props = district["properties"]
                    rows.append({
                        **common,
                        "district_id": district_props.get("canonical_id", ""),
                        "district_name": district_props.get("canonical_name", ""),
                        "district_region_id": district_props.get("canonical_region_id", ""),
                        "district_region_name": district_props.get("canonical_region_name", ""),
                        "intersection_area": "",
                        "intersection_area_unit": "",
                        "district_overlap_pct": "",
                        "ipc_area_overlap_pct": "",
                        "mapping_type": "reference_point_within_district_not_area_mapping",
                        "ambiguous": True,
                        "eligible_for_areal_weighting": False,
                        "notes": "District contains the supplied IPC reference point only; this does not prove that the IPC population or label belongs to that district.",
                    })
            continue

        if geom_type not in {"Polygon", "MultiPolygon"}:
            rows.append({
                **common,
                "mapping_type": "unsupported_geometry",
                "ambiguous": True,
                "eligible_for_areal_weighting": False,
                "notes": "No district assignment was attempted for this geometry type.",
            })
            continue

        ipc_equal_area = transform(to_equal_area, geom)
        ipc_area_km2 = ipc_equal_area.area / 1_000_000
        overlaps: list[dict[str, Any]] = []
        for district in districts:
            if not geom.intersects(district["geometry"]):
                continue
            intersection = ipc_equal_area.intersection(district["equal_area"])
            intersection_km2 = intersection.area / 1_000_000
            if intersection_km2 <= 0:
                continue
            district_pct = 100 * intersection_km2 / district["area_km2"] if district["area_km2"] else 0
            ipc_pct = 100 * intersection_km2 / ipc_area_km2 if ipc_area_km2 else 0
            overlaps.append({
                "district": district,
                "intersection_area_km2": intersection_km2,
                "district_overlap_pct": district_pct,
                "ipc_area_overlap_pct": ipc_pct,
            })

        total_covered_pct = sum(item["ipc_area_overlap_pct"] for item in overlaps)
        substantive = [item for item in overlaps if item["ipc_area_overlap_pct"] >= MIN_SUBSTANTIVE_IPC_PERCENT]
        is_multi = len(substantive) > 1
        coverage_incomplete = total_covered_pct < 99.0 or total_covered_pct > 101.0
        area_ambiguous = is_multi or coverage_incomplete
        polygon_summaries.append({
            "ipc_area_id": area_id,
            "title": title,
            "ipc_area_km2": ipc_area_km2,
            "district_intersections": len(overlaps),
            "substantive_district_intersections": len(substantive),
            "canonical_district_coverage_pct": total_covered_pct,
            "ambiguous": area_ambiguous,
        })

        if not overlaps:
            rows.append({
                **common,
                "mapping_type": "polygon_no_overlap",
                "ambiguous": True,
                "eligible_for_areal_weighting": False,
                "notes": "IPC polygon has no positive-area intersection with the canonical district layer.",
            })
            continue

        for item in overlaps:
            district_props = item["district"]["properties"]
            is_sliver = item["ipc_area_overlap_pct"] < MIN_SUBSTANTIVE_IPC_PERCENT
            if is_sliver:
                mapping_type = "boundary_sliver_preserved"
            elif is_multi:
                mapping_type = "polygon_overlap_multi_district"
            elif coverage_incomplete:
                mapping_type = "polygon_partial_single_district"
            else:
                mapping_type = "polygon_overlap_single_district"
            rows.append({
                **common,
                "district_id": district_props.get("canonical_id", ""),
                "district_name": district_props.get("canonical_name", ""),
                "district_region_id": district_props.get("canonical_region_id", ""),
                "district_region_name": district_props.get("canonical_region_name", ""),
                "intersection_area": round(item["intersection_area_km2"], 6),
                "intersection_area_unit": "km2",
                "district_overlap_pct": round(item["district_overlap_pct"], 6),
                "ipc_area_overlap_pct": round(item["ipc_area_overlap_pct"], 6),
                "mapping_type": mapping_type,
                "ambiguous": area_ambiguous,
                "eligible_for_areal_weighting": not is_sliver,
                "notes": "Equal-area intersection in EPSG:6933; no label assignment is implied.",
            })

    polygon_coverage = [item["canonical_district_coverage_pct"] for item in polygon_summaries]
    snapshot_candidates = infer_snapshot_periods(ipc.get("features", []))
    point_rows_with_area = sum(
        row["ipc_geometry_type"] in {"Point", "MultiPoint"}
        and any(row.get(field) not in ("", None) for field in ("intersection_area", "district_overlap_pct", "ipc_area_overlap_pct"))
        for row in rows
    )
    polygon_percentage_errors = sum(
        row["ipc_geometry_type"] in {"Polygon", "MultiPolygon"}
        and row.get("ipc_area_overlap_pct") not in ("", None)
        and not (0 <= float(row["ipc_area_overlap_pct"]) <= 100.000001)
        for row in rows
    )
    district_percentage_errors = sum(
        row["ipc_geometry_type"] in {"Polygon", "MultiPolygon"}
        and row.get("district_overlap_pct") not in ("", None)
        and not (0 <= float(row["district_overlap_pct"]) <= 100.000001)
        for row in rows
    )
    mapped_area_ids = {row["ipc_area_id"] for row in rows}
    source_area_ids = {str(feature.get("properties", {}).get("aar_id", "")) for feature in ipc.get("features", [])}
    validation_checks = {
        "every_source_feature_has_mapping_record": mapped_area_ids == source_area_ids,
        "point_rows_have_blank_area_metrics": point_rows_with_area == 0,
        "polygon_ipc_overlap_percentages_in_range": polygon_percentage_errors == 0,
        "polygon_district_overlap_percentages_in_range": district_percentage_errors == 0,
        "all_polygon_features_intersect_at_least_one_district": all(item["district_intersections"] > 0 for item in polygon_summaries),
        "all_point_features_have_exactly_one_container": point_match_counts == Counter({"1": geometry_counts.get("Point", 0) + geometry_counts.get("MultiPoint", 0)}),
    }
    if not all(validation_checks.values()):
        raise ValueError(f"IPC geographic mapping validation failed: {validation_checks}")

    summary = {
        "generated_at": NOW,
        "method_version": "1.0",
        "source_crs": "EPSG:4326",
        "area_calculation_crs": EQUAL_AREA_CRS,
        "minimum_substantive_ipc_overlap_pct": MIN_SUBSTANTIVE_IPC_PERCENT,
        "inputs": {
            str(IPC_PATH.relative_to(PROJECT)).replace("\\", "/"): sha256(IPC_PATH),
            str(IPC_AREA_CSV.relative_to(PROJECT)).replace("\\", "/"): sha256(IPC_AREA_CSV),
            str(DISTRICT_PATH.relative_to(PROJECT)).replace("\\", "/"): sha256(DISTRICT_PATH),
        },
        "ipc_feature_count": len(ipc.get("features", [])),
        "mapping_row_count": len(rows),
        "geometry_counts": dict(sorted(geometry_counts.items())),
        "admin_type_counts": dict(sorted(admin_type_counts.items())),
        "analysis_ids": sorted({str(feature.get("properties", {}).get("anl_id", "")) for feature in ipc.get("features", [])}),
        "ipc_period_codes": sorted({str(feature.get("properties", {}).get("ipc_period", "")) for feature in ipc.get("features", [])}),
        "snapshot_period_candidates_from_exact_title_and_population_matches": snapshot_candidates,
        "best_supported_snapshot_period": snapshot_candidates[0] if snapshot_candidates else None,
        "snapshot_period_inference_status": "BEST_SIGNATURE_MATCH_NOT_EXPLICIT_ANALYSIS_ID_JOIN" if snapshot_candidates else "UNRESOLVED",
        "repaired_for_overlay_only": {"ipc_features": repaired_ipc, "district_features": repaired_districts},
        "polygon_area_count": len(polygon_summaries),
        "polygon_single_substantive_district_count": sum(item["substantive_district_intersections"] == 1 for item in polygon_summaries),
        "polygon_multi_substantive_district_count": sum(item["substantive_district_intersections"] > 1 for item in polygon_summaries),
        "polygon_no_substantive_district_count": sum(item["substantive_district_intersections"] == 0 for item in polygon_summaries),
        "polygon_ambiguous_count": sum(bool(item["ambiguous"]) for item in polygon_summaries),
        "polygon_canonical_coverage_pct": {
            "minimum": min(polygon_coverage) if polygon_coverage else None,
            "maximum": max(polygon_coverage) if polygon_coverage else None,
            "mean": sum(polygon_coverage) / len(polygon_coverage) if polygon_coverage else None,
        },
        "point_container_match_counts": dict(sorted(point_match_counts.items())),
        "mapping_type_counts": dict(sorted(Counter(row["mapping_type"] for row in rows).items())),
        "unique_ambiguous_ipc_area_count": len({row["ipc_area_id"] for row in rows if bool(row["ambiguous"])}),
        "eligible_polygon_overlap_row_count": sum(bool(row["eligible_for_areal_weighting"]) for row in rows),
        "validation_checks": validation_checks,
        "polygon_summaries": polygon_summaries,
        "scientific_interpretation": {
            "polygon_features": "Use overlap weights; do not collapse multi-district IPC analysis areas to one district.",
            "point_features": "Urban/IDP points are reference/display locations, not footprint geometry; areal weights are undefined.",
            "temporal_scope": "The GeoJSON is a snapshot. Exact title matching identifies candidate assessment periods but does not prove historical boundary stability.",
        },
    }
    return rows, summary


def point_district(point: Any, districts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [district for district in districts if district["geometry"].covers(point)]


def resolve_wfp_banadir() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    districts_fc = load_json(DISTRICT_PATH)
    districts = []
    for feature in districts_fc.get("features", []):
        geom, _ = repaired_geometry(feature["geometry"])
        districts.append({"geometry": geom, "properties": feature.get("properties", {})})

    market_registry: dict[str, dict[str, str]] = {}
    with WFP_MARKET_PATH.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            if row.get("admin1") == "Banadir" and row.get("admin2") == "Banadir":
                market_registry[str(row.get("market_id", ""))] = row

    price_market_ids: set[str] = set()
    price_rows = 0
    with WFP_PRICE_PATH.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            if row.get("admin1") == "Banadir" and row.get("admin2") == "Banadir":
                price_rows += 1
                price_market_ids.add(str(row.get("market_id", "")))
                market_registry.setdefault(str(row.get("market_id", "")), row)

    resolution_rows: list[dict[str, Any]] = []
    for market_id, market in sorted(market_registry.items()):
        try:
            from shapely.geometry import Point

            point = Point(float(market["longitude"]), float(market["latitude"]))
            matches = point_district(point, districts)
        except (KeyError, TypeError, ValueError):
            matches = []
        if len(matches) == 1:
            props = matches[0]["properties"]
            district_id = props.get("canonical_id", "")
            district_name = props.get("canonical_name", "")
            status = "POINT_RESOLVED_SOURCE_LABEL_QUARANTINED"
            method = "market_coordinate_point_in_polygon"
            review = False
        else:
            district_id = ""
            district_name = ""
            status = "QUARANTINED"
            method = "unresolved_point_container" if matches else "point_outside_or_invalid"
            review = True
        resolution_rows.append({
            "source_admin1": market.get("admin1", ""),
            "source_admin2": market.get("admin2", ""),
            "market_id": market_id,
            "market_name": market.get("market", ""),
            "latitude": market.get("latitude", ""),
            "longitude": market.get("longitude", ""),
            "canonical_district_id": district_id,
            "canonical_district_name": district_name,
            "resolution_method": method,
            "source_label_status": "provider_admin2_duplicates_admin1_not_canonical_district",
            "status": status,
            "review_required": review,
        })
    return resolution_rows, {
        "provider_admin2_value": "Banadir",
        "price_rows": price_rows,
        "price_market_ids": sorted(price_market_ids),
        "registry_markets": len(market_registry),
        "point_resolved_markets": sum(row["status"] == "POINT_RESOLVED_SOURCE_LABEL_QUARANTINED" for row in resolution_rows),
        "quarantined_markets": sum(row["status"] == "QUARANTINED" for row in resolution_rows),
        "conclusion": "HDX/WFP encodes Banadir as #adm2+name, but it duplicates admin1 and does not name a canonical district. Preserve and quarantine that source label; use market coordinates for a separate point-to-district relationship without overwriting admin2.",
    }


def update_geographic_crosswalk(resolution_rows: list[dict[str, Any]]) -> None:
    path = DATA / "metadata" / "geographic_crosswalk.csv"
    columns = ["source_dataset", "geography_level", "source_name", "canonical_name", "canonical_id", "match_method", "confidence", "review_required"]
    rows: list[dict[str, Any]] = []
    if path.exists():
        with path.open(newline="", encoding="utf-8-sig") as stream:
            for row in csv.DictReader(stream):
                if row.get("source_dataset") == "wfp_market_prices" and row.get("geography_level") == "market_point_to_district":
                    continue
                if row.get("source_dataset") == "wfp_market_prices" and row.get("geography_level") == "district" and row.get("source_name") == "Banadir":
                    row["match_method"] = "quarantined_provider_admin2_not_canonical_district"
                    row["confidence"] = "0.0"
                    row["review_required"] = "True"
                rows.append(row)
    for item in resolution_rows:
        rows.append({
            "source_dataset": "wfp_market_prices",
            "geography_level": "market_point_to_district",
            "source_name": f"{item['market_name']} (market_id={item['market_id']})",
            "canonical_name": item["canonical_district_name"],
            "canonical_id": item["canonical_district_id"],
            "match_method": item["resolution_method"],
            "confidence": "1.0" if not item["review_required"] else "0.0",
            "review_required": str(bool(item["review_required"])),
        })
    rows.sort(key=lambda row: (row.get("source_dataset", ""), row.get("geography_level", ""), row.get("source_name", "")))
    atomic_csv(path, rows, columns)


def methodology(summary: dict[str, Any], banadir: dict[str, Any]) -> str:
    geom = summary["geometry_counts"]
    periods = summary["snapshot_period_candidates_from_exact_title_and_population_matches"]
    best_period = summary.get("best_supported_snapshot_period") or {}
    period_text = ", ".join(
        f"{item['date_of_analysis']} ({item['from']} to {item['to']}; "
        f"{item['population_match_count']}/{item['geojson_feature_count']} totals and "
        f"{item['phase_value_match_count']}/{item['phase_value_comparison_count']} phase values match)"
        for item in periods
    ) or "not inferable"
    return f"""# IPC geographic mapping methodology

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
- IPC snapshot analysis ID(s): {", ".join(summary["analysis_ids"])}.
- Geometry inventory: {geom.get("Polygon", 0)} Polygon, {geom.get("MultiPolygon", 0)} MultiPolygon,
  {geom.get("Point", 0)} Point features.
- Exact-title candidate snapshot period(s): {period_text}.

The best-supported period is **{best_period.get('date_of_analysis', 'unresolved')}**
({best_period.get('from', '')} to {best_period.get('to', '')}), selected by the highest exact
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
6. Preserve overlaps below {MIN_SUBSTANTIVE_IPC_PERCENT}% as `boundary_sliver_preserved`, but mark them
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

Observed affected price rows: {banadir["price_rows"]}. Registry markets: {banadir["registry_markets"]}.
Point-resolved markets: {banadir["point_resolved_markets"]}. Quarantined points: {banadir["quarantined_markets"]}.

Authoritative metadata provenance is preserved in `data/metadata/hdx_market_package.json`; it records
WFP as the organization, Registry as the methodology, market coordinates, HXL `#adm1+name` and
`#adm2+name` semantics, and the CC BY-IGO licence.

## Outputs

- `data/processed/food_security/ipc_geographic_mapping.csv`
- `data/processed/food_security/ipc_geographic_mapping.json`
- `data/processed/market_prices/wfp_banadir_geographic_resolution.csv`
- `data/metadata/geographic_crosswalk.csv`
"""


def generate_outputs() -> dict[str, Any]:
    """Generate all mapping artifacts and return a compact validation result."""
    rows, summary = build_ipc_mapping()
    banadir_rows, banadir_summary = resolve_wfp_banadir()
    summary["wfp_banadir"] = banadir_summary
    atomic_csv(CSV_OUTPUT, rows, MAPPING_COLUMNS)
    atomic_json(JSON_OUTPUT, {"summary": summary, "records": rows})
    atomic_csv(
        BANADIR_OUTPUT,
        banadir_rows,
        [
            "source_admin1", "source_admin2", "market_id", "market_name", "latitude", "longitude",
            "canonical_district_id", "canonical_district_name", "resolution_method", "source_label_status",
            "status", "review_required",
        ],
    )
    update_geographic_crosswalk(banadir_rows)
    atomic_text(METHOD_PATH, methodology(summary, banadir_summary))
    return {
        "status": "PASS_WITH_DOCUMENTED_AMBIGUITY",
        "ipc_features": summary["ipc_feature_count"],
        "mapping_rows": summary["mapping_row_count"],
        "geometry_counts": summary["geometry_counts"],
        "mapping_type_counts": summary["mapping_type_counts"],
        "polygon_multi_district": summary["polygon_multi_substantive_district_count"],
        "polygon_ambiguous": summary["polygon_ambiguous_count"],
        "polygon_coverage_pct": summary["polygon_canonical_coverage_pct"],
        "point_container_match_counts": summary["point_container_match_counts"],
        "best_supported_snapshot_period": summary["best_supported_snapshot_period"],
        "validation_checks": summary["validation_checks"],
        "wfp_banadir": banadir_summary,
        "outputs": [str(CSV_OUTPUT), str(JSON_OUTPUT), str(BANADIR_OUTPUT), str(METHOD_PATH)],
    }


def main() -> None:
    print(json.dumps(generate_outputs(), indent=2))


if __name__ == "__main__":
    main()
