"""Acquire and validate Somalia district climate history from NASA POWER.

The connector requests one multi-parameter daily time series for each unique
MERRA-2 grid cell nearest to a Somalia district reference point.  Districts
sharing a source cell share the same raw response; this avoids duplicate API
requests and makes the coarse-grid sampling explicit.

Raw provider responses are immutable JSON.  Derived daily and dekadal tables
are gzip-compressed CSV files so the repository does not need redundant global
rasters.  No model is trained by this script.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
BOUNDARIES = ROOT / "processed" / "boundaries" / "som_admin2_canonical.geojson"
RAW_DIR = ROOT / "raw" / "climate" / "nasa_power_merra2"
PROCESSED_DIR = ROOT / "processed" / "climate"
METADATA_DIR = ROOT / "metadata"
AUTH_REPORT = METADATA_DIR / "earthdata_auth_audit.json"
MANIFEST = METADATA_DIR / "nasa_power_history_manifest.json"
MAPPING = METADATA_DIR / "nasa_power_district_grid_mapping.csv"
VALIDATION = METADATA_DIR / "nasa_power_history_validation.json"
USER_AGENT = "Somalia-AI-Phase01/1.0 (governed research connector)"
PARAMETERS = ("T2M", "T2M_MAX", "T2M_MIN", "GWETTOP", "GWETROOT")
FILL_VALUE = -999.0


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    partial.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(partial, path)


@contextmanager
def atomic_deterministic_gzip_text(path: Path) -> Iterable[Any]:
    """Write a deterministic gzip text file and expose it only when complete."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    try:
        with partial.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as output:
                    yield output
        os.replace(partial, path)
    finally:
        if partial.exists():
            partial.unlink()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def auth_audit() -> dict[str, Any]:
    """Report credential mechanism availability without reading secret values."""
    home = Path.home()
    credential_paths = [
        home / ".netrc",
        home / "_netrc",
        home / ".urs_cookies",
        home / ".earthaccess",
        home / ".cdsapirc",
    ]
    files: list[dict[str, Any]] = []
    for path in credential_paths:
        entry: dict[str, Any] = {"name": path.name, "exists": path.exists()}
        if path.exists() and path.is_file():
            entry["size_bytes"] = path.stat().st_size
            if path.name in {".netrc", "_netrc"}:
                # Machine hostnames are configuration, not credentials. Never
                # include login, password, token, or cookie values.
                text = path.read_text(encoding="utf-8", errors="replace")
                entry["machine_entries"] = sorted(
                    set(re.findall(r"(?im)^\s*machine\s+([^\s]+)", text))
                )
                entry["has_login_field"] = bool(re.search(r"(?im)^\s*login\s+\S+", text))
                entry["has_password_field"] = bool(re.search(r"(?im)^\s*password\s+\S+", text))
        files.append(entry)

    environment_names = sorted(
        name
        for name in os.environ
        if any(
            marker in name.upper()
            for marker in ("EARTHDATA", "EARTHACCESS", "NASA_TOKEN", "URS_", "CMR_", "CDSAPI")
        )
    )
    modules = {
        name: importlib.util.find_spec(name) is not None
        for name in ("earthaccess", "cdsapi", "h5py", "rasterio", "xarray")
    }
    legacy_script = ROOT / "3863313648-download.sh"
    legacy: dict[str, Any] = {"exists": legacy_script.exists()}
    if legacy_script.exists():
        content = legacy_script.read_text(encoding="utf-8", errors="replace")
        legacy.update(
            {
                "interactive_password_prompt": bool(re.search(r"(?i)read\s+.*pass|password", content)),
                "embedded_username_field": bool(re.search(r"(?i)(username|user(name)?)\s*=", content)),
                "embedded_password_assignment": bool(
                    re.search(r"(?im)^\s*(password|passwd|pwd)\s*=\s*[^\s\"']+", content)
                ),
            }
        )

    unattended = bool(
        environment_names
        or any(
            item.get("exists")
            and (
                item["name"] not in {".netrc", "_netrc"}
                or (
                    "urs.earthdata.nasa.gov" in item.get("machine_entries", [])
                    and item.get("has_login_field")
                    and item.get("has_password_field")
                )
            )
            for item in files
            if item["name"] != ".cdsapirc"
        )
    )
    report = {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "credential_files": files,
        "matching_environment_variable_names": environment_names,
        "python_modules": modules,
        "legacy_earthdata_download_script": legacy,
        "earthdata_unattended_auth_available": unattended,
        "smap_historical_automation_status": (
            "CREDENTIAL_MECHANISM_PRESENT_REQUIRES_PROVIDER_TEST"
            if unattended
            else "BLOCKED_NO_NONINTERACTIVE_CREDENTIALS"
        ),
        "security_note": "No credential, token, password, cookie, or environment-variable value was recorded.",
    }
    atomic_json(AUTH_REPORT, report)
    return report


def quantize_power_cell(latitude: float, longitude: float) -> tuple[float, float]:
    """Nearest native MERRA-2 0.5 x 0.625 degree grid-cell centre."""
    grid_lat = round((latitude + 90.0) / 0.5) * 0.5 - 90.0
    grid_lon = round((longitude + 180.0) / 0.625) * 0.625 - 180.0
    return round(grid_lat, 6), round(grid_lon, 6)


def load_district_mapping() -> tuple[list[dict[str, Any]], dict[str, tuple[float, float]]]:
    boundary = json.loads(BOUNDARIES.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    cells: dict[str, tuple[float, float]] = {}
    for feature in boundary["features"]:
        properties = feature["properties"]
        latitude = float(properties["center_lat"])
        longitude = float(properties["center_lon"])
        grid_lat, grid_lon = quantize_power_cell(latitude, longitude)
        cell_id = f"lat{grid_lat:+07.3f}_lon{grid_lon:+08.3f}".replace("+", "p").replace("-", "m")
        cells[cell_id] = (grid_lat, grid_lon)
        rows.append(
            {
                "district_id": properties["canonical_id"],
                "district_name": properties["canonical_name"],
                "region_id": properties["canonical_region_id"],
                "region_name": properties["canonical_region_name"],
                "district_reference_latitude": latitude,
                "district_reference_longitude": longitude,
                "power_grid_id": cell_id,
                "power_grid_latitude": grid_lat,
                "power_grid_longitude": grid_lon,
                "mapping_method": "nearest_MERRA2_cell_to_authoritative_boundary_reference_point",
            }
        )
    MAPPING.parent.mkdir(parents=True, exist_ok=True)
    with MAPPING.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows, cells


def power_url(latitude: float, longitude: float, start: str, end: str) -> str:
    query = urllib.parse.urlencode(
        {
            "parameters": ",".join(PARAMETERS),
            "community": "AG",
            "longitude": longitude,
            "latitude": latitude,
            "start": start,
            "end": end,
            "format": "JSON",
            "time-standard": "UTC",
        }
    )
    return f"https://power.larc.nasa.gov/api/temporal/daily/point?{query}"


def read_manifest() -> dict[str, Any]:
    if not MANIFEST.exists():
        return {"schema_version": 1, "downloads": {}}
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def download_cell(
    cell_id: str,
    latitude: float,
    longitude: float,
    start: str,
    end: str,
    retries: int = 4,
) -> dict[str, Any]:
    destination = RAW_DIR / f"nasa_power_daily_{cell_id}_{start}_{end}.json"
    url = power_url(latitude, longitude, start, end)
    disposition = "SKIPPED_EXISTING"
    if not destination.exists() or destination.stat().st_size == 0:
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".part")
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(request, timeout=900) as response, partial.open("wb") as output:
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
                payload = json.loads(partial.read_text(encoding="utf-8"))
                parameter = payload.get("properties", {}).get("parameter", {})
                missing = [name for name in PARAMETERS if name not in parameter]
                if missing:
                    raise RuntimeError(f"POWER response omitted parameters: {missing}")
                os.replace(partial, destination)
                disposition = "COMPLETE"
                break
            except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
                last_error = exc
                if partial.exists():
                    partial.unlink()
                if attempt == retries:
                    return {
                        "provider": "NASA POWER",
                        "dataset": "MERRA-2/GEOS daily meteorology",
                        "version": "POWER Release 10",
                        "source_url": url,
                        "local_path": destination.relative_to(PROJECT_ROOT).as_posix(),
                        "reference_date": f"{start}/{end}",
                        "downloaded_at": datetime.now(timezone.utc).isoformat(),
                        "size_bytes": 0,
                        "checksum_sha256": None,
                        "status": "FAILED",
                        "error": str(last_error),
                    }
                time.sleep(min(2**attempt, 20))
    return {
        "provider": "NASA POWER",
        "dataset": "MERRA-2/GEOS daily meteorology",
        "version": "POWER Release 10",
        "source_url": url,
        "local_path": destination.relative_to(PROJECT_ROOT).as_posix(),
        "reference_date": f"{start}/{end}",
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "size_bytes": destination.stat().st_size,
        "checksum_sha256": sha256(destination),
        "status": disposition,
    }


def download_history(start: str, end: str, workers: int, limit_cells: int | None) -> dict[str, Any]:
    rows, cells = load_district_mapping()
    selected = sorted(cells.items())[:limit_cells] if limit_cells else sorted(cells.items())
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(download_cell, cell_id, lat, lon, start, end): cell_id
            for cell_id, (lat, lon) in selected
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(f"{result['status']}: {futures[future]}")
    manifest = read_manifest()
    for result in results:
        manifest["downloads"][result["local_path"]] = result
    manifest.update(
        {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "parameters": list(PARAMETERS),
            "district_count": len(rows),
            "unique_source_cell_count": len(cells),
            "requested_cell_count": len(selected),
            "status_counts": {
                status: sum(item.get("status") == status for item in manifest["downloads"].values())
                for status in sorted({item.get("status") for item in manifest["downloads"].values()})
            },
            "total_size_bytes": sum(int(item.get("size_bytes", 0)) for item in manifest["downloads"].values()),
        }
    )
    atomic_json(MANIFEST, manifest)
    failures = [item for item in results if item["status"] == "FAILED"]
    if failures:
        raise RuntimeError(f"{len(failures)} NASA POWER downloads failed; see {MANIFEST}")
    return manifest


def date_keys(start: str, end: str) -> list[str]:
    start_date = date(int(start[:4]), int(start[4:6]), int(start[6:8]))
    end_date = date(int(end[:4]), int(end[4:6]), int(end[6:8]))
    count = (end_date - start_date).days + 1
    return [(start_date.fromordinal(start_date.toordinal() + offset)).strftime("%Y%m%d") for offset in range(count)]


def value_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isclose(number, FILL_VALUE) else number


def dekad_for(day: date) -> int:
    return 1 if day.day <= 10 else 2 if day.day <= 20 else 3


def mean(values: Iterable[float]) -> float | None:
    clean = list(values)
    return sum(clean) / len(clean) if clean else None


def process_history(start: str, end: str) -> dict[str, Any]:
    mapping, cells = load_district_mapping()
    expected = date_keys(start, end)
    cell_values: dict[str, dict[str, dict[str, float | None]]] = {}
    units: dict[str, str] = {}
    missing_files: list[str] = []
    for cell_id in sorted(cells):
        path = RAW_DIR / f"nasa_power_daily_{cell_id}_{start}_{end}.json"
        if not path.exists():
            missing_files.append(path.relative_to(PROJECT_ROOT).as_posix())
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        parameters = payload.get("properties", {}).get("parameter", {})
        api_units = payload.get("parameters", {})
        for name in PARAMETERS:
            descriptor = api_units.get(name, {}) if isinstance(api_units, dict) else {}
            if isinstance(descriptor, dict) and descriptor.get("units"):
                units[name] = descriptor["units"]
        cell_values[cell_id] = {
            key: {name: value_or_none(parameters.get(name, {}).get(key)) for name in PARAMETERS}
            for key in expected
        }
    if missing_files:
        raise RuntimeError(f"Missing {len(missing_files)} raw POWER responses")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    daily_path = PROCESSED_DIR / f"nasa_power_district_daily_{start}_{end}.csv.gz"
    daily_fields = [
        "district_id", "district_name", "region_id", "region_name", "power_grid_id", "date",
        "t2m_c", "t2m_max_c", "t2m_min_c", "gwet_top_relative", "gwet_root_relative",
        "source", "source_version", "time_standard", "mapping_method",
    ]
    daily_missing = {name: 0 for name in PARAMETERS}
    ranges: dict[str, list[float]] = {name: [] for name in PARAMETERS}
    dekad_accumulator: dict[tuple[str, int, int, int], dict[str, Any]] = {}
    with atomic_deterministic_gzip_text(daily_path) as output:
        writer = csv.DictWriter(output, fieldnames=daily_fields)
        writer.writeheader()
        for district in mapping:
            cell_id = district["power_grid_id"]
            for key in expected:
                day = datetime.strptime(key, "%Y%m%d").date()
                values = cell_values[cell_id][key]
                for name, value in values.items():
                    if value is None:
                        daily_missing[name] += 1
                    else:
                        ranges[name].append(value)
                writer.writerow(
                    {
                        "district_id": district["district_id"],
                        "district_name": district["district_name"],
                        "region_id": district["region_id"],
                        "region_name": district["region_name"],
                        "power_grid_id": cell_id,
                        "date": day.isoformat(),
                        "t2m_c": values["T2M"],
                        "t2m_max_c": values["T2M_MAX"],
                        "t2m_min_c": values["T2M_MIN"],
                        "gwet_top_relative": values["GWETTOP"],
                        "gwet_root_relative": values["GWETROOT"],
                        "source": "NASA POWER (MERRA-2/GEOS)",
                        "source_version": "POWER Release 10",
                        "time_standard": "UTC",
                        "mapping_method": district["mapping_method"],
                    }
                )
                dekad_key = (district["district_id"], day.year, day.month, dekad_for(day))
                bucket = dekad_accumulator.setdefault(
                    dekad_key,
                    {
                        "district": district,
                        "dates": [],
                        **{name: [] for name in PARAMETERS},
                    },
                )
                bucket["dates"].append(day)
                for name, value in values.items():
                    if value is not None:
                        bucket[name].append(value)

    # Climatology is computed by month/dekad over 2001-2020 when available.
    climatology_values: dict[tuple[str, int, int], list[float]] = {}
    for (district_id, year, month, dekad), bucket in dekad_accumulator.items():
        if 2001 <= year <= 2020 and bucket["T2M"]:
            climatology_values.setdefault((district_id, month, dekad), []).append(mean(bucket["T2M"]))
    climatology = {key: mean(values) for key, values in climatology_values.items()}

    dekad_path = PROCESSED_DIR / f"nasa_power_district_dekadal_{start}_{end}.csv.gz"
    dekad_fields = [
        "district_id", "district_name", "region_id", "region_name", "year", "month", "dekad",
        "period_start", "period_end", "observed_days", "t2m_mean_c", "t2m_max_c", "t2m_min_c",
        "t2m_anomaly_c_2001_2020", "gwet_top_mean_relative", "gwet_root_mean_relative",
        "source", "source_version",
    ]
    with atomic_deterministic_gzip_text(dekad_path) as output:
        writer = csv.DictWriter(output, fieldnames=dekad_fields)
        writer.writeheader()
        for (district_id, year, month, dekad), bucket in sorted(dekad_accumulator.items()):
            t2m_mean = mean(bucket["T2M"])
            normal = climatology.get((district_id, month, dekad))
            district = bucket["district"]
            writer.writerow(
                {
                    "district_id": district_id,
                    "district_name": district["district_name"],
                    "region_id": district["region_id"],
                    "region_name": district["region_name"],
                    "year": year,
                    "month": month,
                    "dekad": dekad,
                    "period_start": min(bucket["dates"]).isoformat(),
                    "period_end": max(bucket["dates"]).isoformat(),
                    "observed_days": len(bucket["dates"]),
                    "t2m_mean_c": t2m_mean,
                    "t2m_max_c": max(bucket["T2M_MAX"]) if bucket["T2M_MAX"] else None,
                    "t2m_min_c": min(bucket["T2M_MIN"]) if bucket["T2M_MIN"] else None,
                    "t2m_anomaly_c_2001_2020": (
                        t2m_mean - normal if t2m_mean is not None and normal is not None else None
                    ),
                    "gwet_top_mean_relative": mean(bucket["GWETTOP"]),
                    "gwet_root_mean_relative": mean(bucket["GWETROOT"]),
                    "source": "NASA POWER (MERRA-2/GEOS)",
                    "source_version": "POWER Release 10",
                }
            )

    total_rows = len(mapping) * len(expected)
    report = {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "status": "COMPLETE",
        "source": "NASA POWER Release 10, MERRA-2/GEOS meteorology",
        "period": {"start": expected[0], "end": expected[-1], "expected_days": len(expected)},
        "parameters": list(PARAMETERS),
        "provider_reported_units": units,
        "geography": {
            "district_count": len(mapping),
            "unique_source_grid_cells": len(cells),
            "sampling": "nearest native source grid cell to each boundary reference point",
            "source_grid_degrees": {"latitude": 0.5, "longitude": 0.625},
        },
        "daily_rows": total_rows,
        "dekadal_rows": len(dekad_accumulator),
        "missing_values": daily_missing,
        "value_ranges": {
            name: {"minimum": min(values), "maximum": max(values)} if values else None
            for name, values in ranges.items()
        },
        "outputs": {
            "daily": daily_path.relative_to(PROJECT_ROOT).as_posix(),
            "dekadal": dekad_path.relative_to(PROJECT_ROOT).as_posix(),
            "district_grid_mapping": MAPPING.relative_to(PROJECT_ROOT).as_posix(),
        },
        "output_integrity": {
            "daily": {"size_bytes": daily_path.stat().st_size, "checksum_sha256": sha256(daily_path)},
            "dekadal": {"size_bytes": dekad_path.stat().st_size, "checksum_sha256": sha256(dekad_path)},
            "district_grid_mapping": {"size_bytes": MAPPING.stat().st_size, "checksum_sha256": sha256(MAPPING)},
        },
        "scientific_limits": [
            "GWETTOP and GWETROOT are modeled relative wetness indices, not SMAP volumetric soil moisture.",
            "District values sample the nearest coarse source grid cell and are not polygon-area averages.",
            "Near-real-time GEOS values can later be replaced by improved climate-quality MERRA-2 values.",
        ],
    }
    atomic_json(VALIDATION, report)
    return report


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser()
    subparsers = argument_parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("auth-audit")
    for name in ("download", "process", "all"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--start", default="20000101", help="YYYYMMDD")
        subparser.add_argument("--end", default="20251231", help="YYYYMMDD")
        if name in {"download", "all"}:
            subparser.add_argument("--workers", type=int, default=4)
            subparser.add_argument("--limit-cells", type=int)
    return argument_parser


def main() -> int:
    args = parser().parse_args()
    if args.command == "auth-audit":
        report = auth_audit()
        print(report["smap_historical_automation_status"])
    elif args.command == "download":
        download_history(args.start, args.end, args.workers, args.limit_cells)
    elif args.command == "process":
        process_history(args.start, args.end)
    elif args.command == "all":
        auth_audit()
        download_history(args.start, args.end, args.workers, args.limit_cells)
        process_history(args.start, args.end)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
