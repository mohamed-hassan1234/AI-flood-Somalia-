#!/usr/bin/env python3
"""Validate the sourced FAO SWALIM station metadata against project observations and boundaries."""

from __future__ import annotations

import csv
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from pyproj import Geod
from shapely.geometry import Point, shape
from shapely.ops import nearest_points


ROOT = Path(__file__).resolve().parents[2]
STATIONS_CSV = ROOT / "data" / "processed" / "river_station_metadata.csv"
STATIONS_JSON = ROOT / "data" / "processed" / "river_station_metadata.json"
OBSERVATIONS = ROOT / "data" / "processed" / "river_levels" / "river_levels_canonical.csv"
BOUNDARIES = ROOT / "data" / "som_admin_boundaries.geojson.zip"
OUTPUT = ROOT / "data" / "metadata" / "river_station_metadata_validation.json"


def main() -> None:
    with STATIONS_CSV.open(encoding="utf-8", newline="") as source:
        stations = list(csv.DictReader(source))
    json_stations = json.loads(STATIONS_JSON.read_text(encoding="utf-8"))["stations"]

    codes = {row["station_code"] for row in stations}
    expected = {"SH001", "SH002", "SH004", "JB001", "JB009"}

    with OBSERVATIONS.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        observation_rows = 0
        observation_codes: set[str] = set()
        for row in reader:
            observation_rows += 1
            observation_codes.add(row["station_id"].upper())

    with zipfile.ZipFile(BOUNDARIES) as archive:
        district_fc = json.loads(archive.read("som_admin2.geojson"))
    districts = {
        feature["properties"]["adm2_pcode"]: shape(feature["geometry"])
        for feature in district_fc["features"]
    }
    district_names = {
        feature["properties"]["adm2_pcode"]: feature["properties"]["adm2_name"]
        for feature in district_fc["features"]
    }
    geod = Geod(ellps="WGS84")

    checks = []
    for row in stations:
        latitude = float(row["latitude"])
        longitude = float(row["longitude"])
        point = Point(longitude, latitude)
        district = districts[row["canonical_district_id"]]
        point_intersects = district.covers(point)
        nearest_code, nearest_geometry = min(districts.items(), key=lambda item: item[1].distance(point))
        nearest_boundary_point = nearest_points(point, nearest_geometry)[1]
        _, _, nearest_distance_m = geod.inv(
            longitude, latitude, nearest_boundary_point.x, nearest_boundary_point.y
        )
        moderate = float(row["moderate_threshold_m"])
        high = float(row["high_threshold_m"])
        bankfull = float(row["bankfull_threshold_m"])
        checks.append(
            {
                "station_code": row["station_code"],
                "coordinate_range_valid": -2.5 <= latitude <= 12.5 and 40.0 <= longitude <= 52.5,
                "point_intersects_canonical_district": point_intersects,
                "nearest_project_district_id": nearest_code,
                "nearest_project_district_name": district_names[nearest_code],
                "distance_to_nearest_project_district_m": round(nearest_distance_m, 3),
                "threshold_order_valid": moderate < high < bankfull,
                "official_source_hosts_valid": row["metadata_source_url"].startswith(
                    "https://snrfa.faoswalim.org/"
                )
                and row["threshold_source_url"].startswith("https://frrims.faoswalim.org/"),
            }
        )

    result = {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "station_csv_count": len(stations),
        "station_json_count": len(json_stations),
        "expected_station_codes": sorted(expected),
        "metadata_station_codes": sorted(codes),
        "observation_station_codes": sorted(observation_codes),
        "observation_rows": observation_rows,
        "all_expected_metadata_codes_present": codes == expected,
        "all_observation_codes_have_metadata": observation_codes <= codes,
        "csv_json_station_codes_match": codes == {row["station_code"] for row in json_stations},
        "spatial_exception_count": sum(
            not row["point_intersects_canonical_district"] for row in checks
        ),
        "station_checks": checks,
    }
    result["passed"] = all(
        [
            result["all_expected_metadata_codes_present"],
            result["all_observation_codes_have_metadata"],
            result["csv_json_station_codes_match"],
            all(
                row["coordinate_range_valid"]
                and row["threshold_order_valid"]
                and row["official_source_hosts_valid"]
                for row in checks
            ),
        ]
    )

    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "observation_rows": observation_rows, "stations": len(stations)}))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
