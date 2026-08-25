"""Non-destructive Phase 01 data inventory and validation utility.

The script treats every source file as immutable. It reads source files and writes
machine-readable audit outputs only under data/metadata.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


GENERATED_DIRECTORIES = {"features", "metadata", "processed", "scripts", "staging"}
DATA_EXTENSIONS = {
    ".csv",
    ".xlsx",
    ".xls",
    ".geojson",
    ".json",
    ".shp",
    ".dbf",
    ".shx",
    ".prj",
    ".tif",
    ".tiff",
    ".nc",
    ".nc4",
    ".hdf",
    ".h5",
    ".zip",
    ".gz",
    ".parquet",
}
DATE_PATTERN = re.compile(r"(?P<year>19\d{2}|20\d{2})[._-](?P<month>0[1-9]|1[0-2])[._-](?P<day>[0-3]\d)")


def optional_imports() -> dict[str, Any]:
    modules: dict[str, Any] = {}
    for name in ("h5py", "openpyxl", "pandas", "rasterio", "xarray"):
        try:
            modules[name] = __import__(name)
        except ImportError:
            modules[name] = None
    return modules


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not any(part.lower() in GENERATED_DIRECTORIES for part in path.relative_to(root).parts[:-1])
    )


def serializable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable(item) for item in value]
    if hasattr(value, "tolist"):
        return serializable(value.tolist())
    return str(value)


def date_from_name(path: Path) -> str | None:
    match = DATE_PATTERN.search(path.name)
    if not match:
        match = re.search(r"_(?P<year>20\d{2})(?P<month>0[1-9]|1[0-2])(?P<day>[0-3]\d)_", path.name)
    if not match:
        return None
    try:
        return datetime(
            int(match.group("year")), int(match.group("month")), int(match.group("day"))
        ).date().isoformat()
    except ValueError:
        return None


def inspect_csv(path: Path) -> dict[str, Any]:
    encodings = ("utf-8-sig", "utf-8", "cp1252")
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            with path.open("r", encoding=encoding, newline="") as stream:
                reader = csv.reader(stream)
                header = next(reader, [])
                rows = 0
                width_counts: Counter[int] = Counter()
                samples: list[list[str]] = []
                for row in reader:
                    rows += 1
                    width_counts[len(row)] += 1
                    if len(samples) < 3:
                        samples.append(row)
            return {
                "readable": True,
                "encoding": encoding,
                "columns": header,
                "column_count": len(header),
                "row_count": rows,
                "row_width_counts": dict(width_counts),
                "sample_rows": samples,
                "schema_consistent": not width_counts or set(width_counts) == {len(header)},
            }
        except (UnicodeDecodeError, csv.Error, OSError) as exc:
            last_error = exc
    return {"readable": False, "error": str(last_error)}


def inspect_excel(path: Path, modules: dict[str, Any]) -> dict[str, Any]:
    openpyxl = modules["openpyxl"]
    if openpyxl is None:
        return {"readable": None, "validation_blocker": "openpyxl is not installed"}
    try:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        sheets = []
        for sheet in workbook.worksheets:
            rows = sheet.iter_rows(values_only=True)
            header = list(next(rows, ()))
            sheets.append(
                {
                    "name": sheet.title,
                    "rows": sheet.max_row,
                    "columns": sheet.max_column,
                    "header": header,
                }
            )
        workbook.close()
        return {"readable": True, "sheets": sheets}
    except Exception as exc:  # workbook parsers expose multiple format-specific errors
        return {"readable": False, "error": f"{type(exc).__name__}: {exc}"}


def _geojson_summary(payload: dict[str, Any]) -> dict[str, Any]:
    features = payload.get("features")
    if payload.get("type") != "FeatureCollection" or not isinstance(features, list):
        return {"valid_feature_collection": False}
    geometry_types = Counter()
    property_keys = Counter()
    empty_geometries = 0
    for feature in features:
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict) or not geometry.get("coordinates"):
            empty_geometries += 1
        else:
            geometry_types[str(geometry.get("type"))] += 1
        properties = feature.get("properties")
        if isinstance(properties, dict):
            property_keys.update(properties.keys())
    return {
        "valid_feature_collection": True,
        "feature_count": len(features),
        "geometry_types": dict(geometry_types),
        "empty_geometries": empty_geometries,
        "property_keys": sorted(property_keys),
        "declared_crs": serializable(payload.get("crs")),
    }


def inspect_geojson(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8-sig") as stream:
            return {"readable": True, **_geojson_summary(json.load(stream))}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"readable": False, "error": str(exc)}


def inspect_zip(path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as archive:
            bad_member = archive.testzip()
            members = [
                {"name": info.filename, "size": info.file_size, "compressed_size": info.compress_size}
                for info in archive.infolist()
            ]
            result: dict[str, Any] = {
                "readable": True,
                "member_count": len(members),
                "members": members,
                "bad_member": bad_member,
            }
            geojson_names = [
                item["name"] for item in members if str(item["name"]).lower().endswith((".geojson", ".json"))
            ]
            if len(geojson_names) == 1:
                with archive.open(geojson_names[0]) as stream:
                    payload = json.loads(stream.read().decode("utf-8-sig"))
                result["geojson"] = _geojson_summary(payload)
            return result
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"readable": False, "error": str(exc)}


def inspect_raster(path: Path, modules: dict[str, Any]) -> dict[str, Any]:
    rasterio = modules["rasterio"]
    if rasterio is None:
        return {"readable": None, "validation_blocker": "rasterio is not installed"}
    try:
        with rasterio.open(path) as dataset:
            result: dict[str, Any] = {
                "readable": True,
                "driver": dataset.driver,
                "width": dataset.width,
                "height": dataset.height,
                "bands": dataset.count,
                "dtypes": dataset.dtypes,
                "crs": str(dataset.crs),
                "bounds": list(dataset.bounds),
                "transform": list(dataset.transform),
                "nodata": dataset.nodata,
                "units": dataset.units,
                "descriptions": dataset.descriptions,
                "tags": dataset.tags(),
            }
            sample = dataset.read(1, out_shape=(1, min(256, dataset.height), min(256, dataset.width)), masked=True)
            if sample.count():
                result["sample_min"] = float(sample.min())
                result["sample_max"] = float(sample.max())
                result["sample_mean"] = float(sample.mean())
                result["sample_valid_fraction"] = float(sample.count() / sample.size)
            else:
                result["sample_valid_fraction"] = 0.0
            return result
    except Exception as exc:
        return {"readable": False, "error": f"{type(exc).__name__}: {exc}"}


def inspect_netcdf(path: Path, modules: dict[str, Any]) -> dict[str, Any]:
    xarray = modules["xarray"]
    first_error: Exception | None = None
    if xarray is not None:
        try:
            dataset = xarray.open_dataset(path, decode_cf=False)
            variables = {}
            for name, variable in dataset.variables.items():
                variables[name] = {
                    "dimensions": list(variable.dims),
                    "shape": list(variable.shape),
                    "dtype": str(variable.dtype),
                    "attributes": serializable(variable.attrs),
                }
            result = {
                "readable": True,
                "dimensions": dict(dataset.sizes),
                "variables": variables,
                "attributes": serializable(dataset.attrs),
            }
            dataset.close()
            return result
        except Exception as exc:
            first_error = exc
    h5py = modules["h5py"]
    if h5py is None:
        return {
            "readable": None if xarray is None else False,
            "validation_blocker": "Neither xarray nor h5py is installed",
            "error": f"{type(first_error).__name__}: {first_error}" if first_error else None,
        }
    try:
        groups: list[str] = []
        datasets: dict[str, Any] = {}
        with h5py.File(path, "r") as handle:
            def visitor(name: str, item: Any) -> None:
                if isinstance(item, h5py.Group):
                    groups.append(name)
                elif isinstance(item, h5py.Dataset):
                    datasets[name] = {
                        "shape": list(item.shape),
                        "dtype": str(item.dtype),
                        "attributes": serializable(dict(item.attrs)),
                    }

            handle.visititems(visitor)
        return {
            "readable": True,
            "reader": "h5py",
            "groups": groups,
            "variables": datasets,
            "xarray_error": (
                f"{type(first_error).__name__}: {first_error}"
                if first_error
                else "xarray is not installed"
            ),
        }
    except Exception as second_error:
        return {
            "readable": False,
            "error": (
                f"xarray={type(first_error).__name__}: {first_error}; "
                if first_error
                else "xarray=not installed; "
            )
            + f"h5py={type(second_error).__name__}: {second_error}",
        }


def inspect_file(path: Path, root: Path, modules: dict[str, Any]) -> dict[str, Any]:
    stat = path.stat()
    suffix = path.suffix.lower()
    record: dict[str, Any] = {
        "path": path.relative_to(root).as_posix(),
        "extension": suffix,
        "size_bytes": stat.st_size,
        "modified_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "sha256": sha256(path),
        "zero_byte": stat.st_size == 0,
        "suspected_partial_download": suffix in {".part", ".partial", ".crdownload", ".tmp"},
        "date_from_filename": date_from_name(path),
        "is_recognized_data_format": suffix in DATA_EXTENSIONS,
    }
    if stat.st_size == 0:
        record["inspection"] = {"readable": False, "error": "zero-byte file"}
    elif suffix == ".csv":
        record["inspection"] = inspect_csv(path)
    elif suffix in {".xlsx", ".xls"}:
        record["inspection"] = inspect_excel(path, modules)
    elif suffix in {".geojson", ".json"}:
        record["inspection"] = inspect_geojson(path)
    elif suffix == ".zip":
        record["inspection"] = inspect_zip(path)
    elif suffix in {".tif", ".tiff", ".hdf"}:
        record["inspection"] = inspect_raster(path, modules)
    elif suffix in {".nc", ".nc4", ".h5"}:
        record["inspection"] = inspect_netcdf(path, modules)
    else:
        record["inspection"] = {"readable": None, "note": "inventory and checksum only"}
    return record


def compact_inventory(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        inspection = record["inspection"]
        rows.append(
            {
                "path": record["path"],
                "extension": record["extension"],
                "size_bytes": record["size_bytes"],
                "modified_utc": record["modified_utc"],
                "sha256": record["sha256"],
                "zero_byte": record["zero_byte"],
                "suspected_partial_download": record["suspected_partial_download"],
                "date_from_filename": record["date_from_filename"],
                "readable": inspection.get("readable"),
                "error": inspection.get("error"),
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(rows[0]) if rows else ["path"]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.data_root.resolve()
    output = root / "metadata"
    output.mkdir(parents=True, exist_ok=True)
    modules = optional_imports()
    files = source_files(root)
    records = [inspect_file(path, root, modules) for path in files]
    hashes: dict[str, list[str]] = defaultdict(list)
    for record in records:
        hashes[record["sha256"]].append(record["path"])
    duplicates = [paths for paths in hashes.values() if len(paths) > 1]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_root": str(root),
        "source_file_count": len(records),
        "total_source_bytes": sum(record["size_bytes"] for record in records),
        "available_python_modules": {name: module is not None for name, module in modules.items()},
        "zero_byte_files": [record["path"] for record in records if record["zero_byte"]],
        "suspected_partial_downloads": [
            record["path"] for record in records if record["suspected_partial_download"]
        ],
        "unreadable_files": [
            record["path"]
            for record in records
            if record["inspection"].get("readable") is False
        ],
        "exact_duplicate_groups": duplicates,
        "files": records,
    }
    with (output / "validation_report.json").open("w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    write_csv(output / "file_inventory.csv", compact_inventory(records))
    print(json.dumps({key: value for key, value in report.items() if key != "files"}, indent=2))
    return 1 if report["zero_byte_files"] or report["unreadable_files"] else 0


if __name__ == "__main__":
    sys.exit(main())
