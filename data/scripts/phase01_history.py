"""Build storage-efficient historical district time-series for Phase 01.

The script streams authoritative compact rasters or reads cloud-optimized
rasters by byte range, then writes district summaries. It does not place global
raster archives in the repository. Every source URL and derived archive
checksum is preserved.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
import threading
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import rasterio
import requests
from affine import Affine
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.features import rasterize
from rasterio.windows import Window, from_bounds
from rasterio.warp import transform_bounds, transform_geom


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "processed"
METADATA = ROOT / "metadata"
BOUNDARIES = PROCESSED / "boundaries" / "som_admin2_canonical.geojson"
HISTORICAL_MANIFEST = METADATA / "historical_archive_manifest.csv"
USER_AGENT = "Somalia-AI-Phase01-History/1.0"
HTTP_LOCAL = threading.local()
SIGN_RATE_LOCK = threading.Lock()
SIGN_NEXT_TIME = 0.0
SOMALIA_BOUNDS = (40.9, -1.8, 51.6, 12.1)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    frame.to_csv(temporary, index=False)
    os.replace(temporary, path)


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def load_districts() -> list[dict[str, Any]]:
    collection = json.loads(BOUNDARIES.read_text(encoding="utf-8"))
    districts = []
    for feature in collection["features"]:
        properties = feature["properties"]
        districts.append(
            {
                "district_id": properties["canonical_id"],
                "district_name": properties["canonical_name"],
                "region_id": properties.get("canonical_region_id"),
                "region_name": properties.get("canonical_region_name"),
                "geometry": feature["geometry"],
            }
        )
    return districts


def bounded_window(dataset: rasterio.DatasetReader, bounds: tuple[float, float, float, float]) -> Window:
    window = from_bounds(*bounds, transform=dataset.transform).round_offsets().round_lengths()
    whole = Window(0, 0, dataset.width, dataset.height)
    return window.intersection(whole)


def date_range(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def chirps_url(day: date) -> str:
    filename = f"chirps-v3.0.rnl.{day:%Y.%m.%d}.tif"
    return (
        "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/p25/"
        f"{day:%Y}/{filename}"
    )


def download_bytes(url: str) -> bytes:
    session = getattr(HTTP_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})
        HTTP_LOCAL.session = session
    response = session.get(url, timeout=180)
    response.raise_for_status()
    return response.content


def _chirps_one(day: date, districts: list[dict[str, Any]], retries: int = 3) -> list[dict[str, Any]]:
    url = chirps_url(day)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            payload = download_bytes(url)
            with MemoryFile(payload) as memory:
                with memory.open() as dataset:
                    window = bounded_window(dataset, SOMALIA_BOUNDS)
                    rainfall = dataset.read(1, window=window, masked=True)
                    transform = dataset.window_transform(window)
                    values = rainfall.filled(np.nan).astype("float64")
                    rows: list[dict[str, Any]] = []
                    for district in districts:
                        # Burn each district separately. Some Somalia boundary sources
                        # contain overlaps; a single categorical burn would let the last
                        # feature erase pixels belonging to an earlier district.
                        inside = rasterize(
                            [(district["geometry"], 1)],
                            out_shape=rainfall.shape,
                            transform=transform,
                            fill=0,
                            dtype="uint8",
                            all_touched=True,
                        ).astype(bool)
                        valid = inside & np.isfinite(values) & (values >= 0)
                        pixels = values[valid]
                        rows.append(
                            {
                                "district_id": district["district_id"],
                                "district_name": district["district_name"],
                                "region_id": district["region_id"],
                                "region_name": district["region_name"],
                                "date": day.isoformat(),
                                "rainfall_mean_mm": float(np.mean(pixels)) if pixels.size else np.nan,
                                "rainfall_max_mm": float(np.max(pixels)) if pixels.size else np.nan,
                                "valid_pixel_fraction": float(pixels.size / inside.sum()) if inside.sum() else 0.0,
                                "source_url": url,
                                "source_version": "CHIRPS v3 daily final rnl p25",
                            }
                        )
                    return rows
        except Exception as error:
            last_error = error
            if attempt < retries:
                time.sleep(min(2**attempt, 10))
    raise RuntimeError(f"CHIRPS failed for {day}: {last_error}")


def valid_chirps_checkpoint(path: Path, start: date, end: date, district_count: int) -> bool:
    """Accept only a structurally complete district-day checkpoint."""
    try:
        frame = pd.read_csv(path, usecols=["district_id", "date", "rainfall_mean_mm"])
        expected_days = (end - start).days + 1
        return (
            len(frame) == expected_days * district_count
            and frame["district_id"].nunique() == district_count
            and frame["date"].nunique() == expected_days
            and not frame.duplicated(["district_id", "date"]).any()
            and frame["date"].min() == start.isoformat()
            and frame["date"].max() == end.isoformat()
            and not frame["rainfall_mean_mm"].isna().any()
        )
    except (OSError, ValueError, KeyError, pd.errors.ParserError):
        return False


def derive_rainfall_features(
    daily: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    daily = daily.sort_values(["district_id", "date"]).copy()
    daily["date"] = pd.to_datetime(daily["date"])
    grouped = daily.groupby("district_id", group_keys=False)
    daily["rainfall_7d_mm"] = grouped["rainfall_mean_mm"].rolling(7, min_periods=7).sum().reset_index(level=0, drop=True)
    daily["rainfall_30d_mm"] = grouped["rainfall_mean_mm"].rolling(30, min_periods=30).sum().reset_index(level=0, drop=True)
    daily["heavy_rain_20mm"] = (daily["rainfall_mean_mm"] >= 20.0).astype("int8")

    def dry_spell(values: pd.Series) -> pd.Series:
        run = 0
        result = []
        for value in values:
            run = run + 1 if pd.notna(value) and value < 1.0 else 0
            result.append(run)
        return pd.Series(result, index=values.index)

    daily["dry_spell_days"] = grouped["rainfall_mean_mm"].transform(dry_spell)
    daily["year"] = daily["date"].dt.year
    daily["month"] = daily["date"].dt.month
    daily["dekad"] = np.select(
        [daily["date"].dt.day <= 10, daily["date"].dt.day <= 20],
        [1, 2],
        default=3,
    )
    daily["dekad_start"] = pd.to_datetime(
        dict(
            year=daily["year"],
            month=daily["month"],
            day=np.select([daily["dekad"] == 1, daily["dekad"] == 2], [1, 11], default=21),
        )
    )
    identifiers = ["district_id", "district_name", "region_id", "region_name", "year", "month", "dekad", "dekad_start"]
    dekad = daily.groupby(identifiers, as_index=False).agg(
        rainfall_mm=("rainfall_mean_mm", "sum"),
        rainfall_daily_mean_mm=("rainfall_mean_mm", "mean"),
        rainfall_daily_max_mm=("rainfall_max_mm", "max"),
        heavy_rain_days=("heavy_rain_20mm", "sum"),
        valid_days=("rainfall_mean_mm", "count"),
        valid_pixel_fraction=("valid_pixel_fraction", "mean"),
        dry_spell_days_end=("dry_spell_days", "last"),
    )
    baseline = (
        dekad.groupby(["district_id", "month", "dekad"])["rainfall_mm"]
        .agg(["mean", "std"])
        .rename(columns={"mean": "baseline_mean_mm", "std": "baseline_std_mm"})
        .reset_index()
    )
    dekad = dekad.merge(baseline, on=["district_id", "month", "dekad"], how="left")
    dekad["rainfall_anomaly_mm"] = dekad["rainfall_mm"] - dekad["baseline_mean_mm"]
    dekad["rainfall_anomaly_z"] = dekad["rainfall_anomaly_mm"] / dekad["baseline_std_mm"].replace(0, np.nan)
    dekad["percent_of_normal"] = 100.0 * dekad["rainfall_mm"] / dekad["baseline_mean_mm"].replace(0, np.nan)
    dekad["source_version"] = "CHIRPS v3 daily final rnl p25; district mean; baseline=local archive years"

    monthly = daily.groupby(
        ["district_id", "district_name", "region_id", "region_name", "year", "month"],
        as_index=False,
    ).agg(
        rainfall_mm=("rainfall_mean_mm", "sum"),
        rainfall_daily_mean_mm=("rainfall_mean_mm", "mean"),
        rainfall_daily_max_mm=("rainfall_max_mm", "max"),
        heavy_rain_days=("heavy_rain_20mm", "sum"),
        valid_days=("rainfall_mean_mm", "count"),
        valid_pixel_fraction=("valid_pixel_fraction", "mean"),
        dry_spell_days_end=("dry_spell_days", "last"),
    )
    monthly_baseline = monthly.groupby(["district_id", "month"])["rainfall_mm"].agg(["mean", "std"]).reset_index()
    monthly_baseline.columns = ["district_id", "month", "baseline_mean_mm", "baseline_std_mm"]
    monthly = monthly.merge(monthly_baseline, on=["district_id", "month"], how="left")
    monthly["rainfall_anomaly_mm"] = monthly["rainfall_mm"] - monthly["baseline_mean_mm"]
    monthly["rainfall_anomaly_z"] = monthly["rainfall_anomaly_mm"] / monthly["baseline_std_mm"].replace(0, np.nan)
    monthly["percent_of_normal"] = 100.0 * monthly["rainfall_mm"] / monthly["baseline_mean_mm"].replace(0, np.nan)
    monthly["month_start"] = pd.to_datetime(dict(year=monthly["year"], month=monthly["month"], day=1))
    monthly["source_version"] = "CHIRPS v3 daily final rnl p25; district monthly aggregate"

    season_names = {1: "Jilaal", 2: "Jilaal", 3: "Jilaal", 4: "Gu", 5: "Gu", 6: "Gu",
                    7: "Xagaa", 8: "Xagaa", 9: "Xagaa", 10: "Deyr", 11: "Deyr", 12: "Deyr"}
    season_order = {"Jilaal": 1, "Gu": 2, "Xagaa": 3, "Deyr": 4}
    monthly["season"] = monthly["month"].map(season_names)
    monthly["season_order"] = monthly["season"].map(season_order)
    seasonal = monthly.groupby(
        ["district_id", "district_name", "region_id", "region_name", "year", "season", "season_order"],
        as_index=False,
    ).agg(
        rainfall_mm=("rainfall_mm", "sum"),
        heavy_rain_days=("heavy_rain_days", "sum"),
        valid_days=("valid_days", "sum"),
        valid_pixel_fraction=("valid_pixel_fraction", "mean"),
    )
    seasonal_baseline = seasonal.groupby(["district_id", "season"])["rainfall_mm"].agg(["mean", "std"]).reset_index()
    seasonal_baseline.columns = ["district_id", "season", "baseline_mean_mm", "baseline_std_mm"]
    seasonal = seasonal.merge(seasonal_baseline, on=["district_id", "season"], how="left")
    seasonal["rainfall_anomaly_mm"] = seasonal["rainfall_mm"] - seasonal["baseline_mean_mm"]
    seasonal["rainfall_anomaly_z"] = seasonal["rainfall_anomaly_mm"] / seasonal["baseline_std_mm"].replace(0, np.nan)
    seasonal["percent_of_normal"] = 100.0 * seasonal["rainfall_mm"] / seasonal["baseline_mean_mm"].replace(0, np.nan)
    seasonal["source_version"] = "CHIRPS v3 daily final rnl p25; Somalia climatological-season aggregate"
    return daily, dekad, monthly, seasonal


def build_chirps(start: date, end: date, workers: int) -> None:
    districts = load_districts()
    years = range(start.year, end.year + 1)
    year_paths: list[Path] = []
    for year in years:
        year_start = max(start, date(year, 1, 1))
        year_end = min(end, date(year, 12, 31))
        output = (
            PROCESSED
            / "rainfall"
            / "chirps_v3_daily_district"
            / f"chirps_v3_daily_district_{year_start}_{year_end}.csv"
        )
        year_paths.append(output)
        if valid_chirps_checkpoint(output, year_start, year_end, len(districts)):
            print(f"SKIP {output.relative_to(ROOT)}")
            continue
        if output.exists():
            print(f"REBUILD invalid checkpoint {output.relative_to(ROOT)}", flush=True)
        rows: list[dict[str, Any]] = []
        days = list(date_range(year_start, year_end))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_chirps_one, day, districts): day for day in days}
            for completed, future in enumerate(as_completed(futures), start=1):
                rows.extend(future.result())
                if completed % 25 == 0 or completed == len(days):
                    print(f"CHIRPS {year}: {completed}/{len(days)} days")
        frame = pd.DataFrame(rows).sort_values(["district_id", "date"])
        atomic_csv(output, frame)
    daily = pd.concat((pd.read_csv(path) for path in year_paths), ignore_index=True)
    daily, dekad, monthly, seasonal = derive_rainfall_features(daily)
    daily_path = PROCESSED / "rainfall" / f"chirps_v3_daily_district_{start}_{end}.csv"
    dekad_path = PROCESSED / "rainfall" / f"chirps_v3_dekad_district_{start}_{end}.csv"
    monthly_path = PROCESSED / "rainfall" / f"chirps_v3_monthly_district_{start}_{end}.csv"
    seasonal_path = PROCESSED / "rainfall" / f"chirps_v3_seasonal_district_{start}_{end}.csv"
    atomic_csv(daily_path, daily)
    atomic_csv(dekad_path, dekad)
    atomic_csv(monthly_path, monthly)
    atomic_csv(seasonal_path, seasonal)
    validation = {
        "dataset": "CHIRPS v3 daily final rnl p25 district time-series",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "expected_days": (end - start).days + 1,
        "actual_days": int(daily["date"].nunique()),
        "districts": int(daily["district_id"].nunique()),
        "daily_rows": len(daily),
        "dekad_rows": len(dekad),
        "monthly_rows": len(monthly),
        "seasonal_rows": len(seasonal),
        "missing_dates": sorted(
            set(day.isoformat() for day in date_range(start, end))
            - set(pd.to_datetime(daily["date"]).dt.date.astype(str))
        ),
        "missing_date_percentage": 100.0 * (
            (end - start).days + 1 - int(daily["date"].nunique())
        ) / ((end - start).days + 1),
        "minimum_valid_pixel_fraction": float(daily["valid_pixel_fraction"].min()),
        "missing_district_day_rows": int(daily["rainfall_mean_mm"].isna().sum()),
        "negative_rainfall_rows": int((daily["rainfall_mean_mm"] < 0).sum()),
        "crs": "EPSG:4326",
        "source_resolution": "0.25 degree",
        "source_nodata": None,
        "invalid_value_rule": "exclude non-finite and negative source values",
        "source_url_template": "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/p25/{YYYY}/chirps-v3.0.rnl.{YYYY.MM.DD}.tif",
        "daily_sha256": sha256(daily_path),
        "dekad_sha256": sha256(dekad_path),
        "monthly_sha256": sha256(monthly_path),
        "seasonal_sha256": sha256(seasonal_path),
        "output_size_bytes": {
            "daily": daily_path.stat().st_size,
            "dekad": dekad_path.stat().st_size,
            "monthly": monthly_path.stat().st_size,
            "seasonal": seasonal_path.stat().st_size,
        },
        "status": (
            "COMPLETE"
            if daily["date"].nunique() == (end - start).days + 1
            and not daily["rainfall_mean_mm"].isna().any()
            else "PARTIAL"
        ),
    }
    atomic_json(METADATA / "chirps_historical_validation.json", validation)
    update_history_manifest(
        provider="UCSB Climate Hazards Center",
        dataset="CHIRPS v3 daily final rnl p25 district archive",
        version="3.0",
        source_url=validation["source_url_template"],
        path=dekad_path,
        reference_date=f"{start}/{end}",
        status=validation["status"],
    )


def request_json(url: str, payload: dict[str, Any] | None = None, retries: int = 5) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(
                url,
                data=data,
                headers={"User-Agent": USER_AGENT, **({"Content-Type": "application/json"} if data else {})},
            )
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.load(response)
        except Exception as error:
            last_error = error
            if attempt < retries:
                time.sleep(min(2**attempt, 30))
    raise RuntimeError(f"JSON request failed after {retries} attempts: {url}: {last_error}")


def sign_url(url: str) -> str:
    global SIGN_NEXT_TIME
    # The public signing service is shared infrastructure. Serialize and pace
    # requests across worker threads to avoid bursts and HTTP 429 responses.
    with SIGN_RATE_LOCK:
        delay = SIGN_NEXT_TIME - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        SIGN_NEXT_TIME = time.monotonic() + 0.25
    response = request_json(
        "https://planetarycomputer.microsoft.com/api/sas/v1/sign?"
        + urllib.parse.urlencode({"href": url})
    )
    return response["href"]


def modis_items(start: date, end: date) -> list[dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    cursor = start
    while cursor <= end:
        # This collection contains both Terra and Aqua and can contain more
        # than one production of a tile. Keep each request safely below the
        # 100-item STAC page limit before filtering to Terra.
        segment_end = min(end, cursor + timedelta(days=30))
        payload = {
            "collections": ["modis-13Q1-061"],
            "bbox": list(SOMALIA_BOUNDS),
            "datetime": f"{cursor.isoformat()}T00:00:00Z/{segment_end.isoformat()}T23:59:59Z",
            "limit": 100,
        }
        response = request_json("https://planetarycomputer.microsoft.com/api/stac/v1/search", payload)
        for item in response.get("features", []):
            item_start_text = item.get("properties", {}).get("start_datetime", "")[:10]
            try:
                item_start = date.fromisoformat(item_start_text)
            except ValueError:
                continue
            if item.get("properties", {}).get("platform") == "terra" and start <= item_start <= end:
                # The host can retain more than one production timestamp for
                # the same product/date/tile/version. Select the newest logical
                # granule rather than double-weighting duplicate productions.
                logical_id = ".".join(item["id"].split(".")[:4])
                existing = items.get(logical_id)
                if existing is None or item["id"] > existing["id"]:
                    items[logical_id] = item
        cursor = segment_end + timedelta(days=1)
    return sorted(items.values(), key=lambda item: (item["properties"].get("start_datetime", ""), item["id"]))


def nominal_modis_dates(start: date, end: date) -> list[str]:
    dates: list[str] = []
    for year in range(start.year, end.year + 1):
        composite_date = date(year, 1, 1)
        while composite_date.year == year:
            if start <= composite_date <= end:
                dates.append(composite_date.isoformat())
            composite_date += timedelta(days=16)
    return dates


def _modis_item_values(item: dict[str, Any], districts: list[dict[str, Any]]) -> dict[str, Any]:
    assets = item["assets"]
    names = {
        "ndvi": "250m_16_days_NDVI",
        "evi": "250m_16_days_EVI",
        "quality": "250m_16_days_VI_Quality",
        "reliability": "250m_16_days_pixel_reliability",
    }
    # All four science assets for one STAC item share the same Azure blob
    # container. A container-scoped SAS query (sr=c) can therefore be obtained
    # once and applied to the sibling assets, greatly reducing calls to the
    # public signing service. Fall back to an individual signature if a future
    # item places an asset in a different container.
    first_name = next(iter(names))
    first_href = assets[names[first_name]]["href"]
    first_signed = sign_url(first_href)
    first_parts = urllib.parse.urlsplit(first_signed)
    first_container = first_parts.path.split("/", 2)[1]
    signed: dict[str, str] = {}
    for name, key in names.items():
        href = assets[key]["href"]
        parts = urllib.parse.urlsplit(href)
        container = parts.path.split("/", 2)[1]
        if parts.netloc == first_parts.netloc and container == first_container:
            signed[name] = urllib.parse.urlunsplit(
                (parts.scheme, parts.netloc, parts.path, first_parts.query, parts.fragment)
            )
        else:
            signed[name] = sign_url(href)
    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        GDAL_HTTP_MULTIRANGE="YES",
        GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
        VSI_CACHE="TRUE",
        VSI_CACHE_SIZE=16_000_000,
    ):
        with rasterio.open(signed["reliability"]) as reference:
            if reference.crs is None or reference.transform.is_identity:
                raise RuntimeError(f"MOD13Q1 item {item['id']} has no usable georeferencing")
            reference_grid = (reference.crs, reference.transform, reference.width, reference.height)
            bounds = transform_bounds("EPSG:4326", reference.crs, *SOMALIA_BOUNDS, densify_pts=21)
            window = bounded_window(reference, bounds)
            # Read the native 250 m product through its 4x overview for
            # district-scale summaries. QA and VI bands use the same nearest
            # neighbour sample grid, so bit fields remain valid and aligned.
            out_shape = (
                max(1, int(np.ceil(window.height / 4))),
                max(1, int(np.ceil(window.width / 4))),
            )
            transform = reference.window_transform(window) * Affine.scale(
                window.width / out_shape[1], window.height / out_shape[0]
            )
            reliability = reference.read(
                1, window=window, out_shape=out_shape, masked=True, resampling=Resampling.nearest
            )
            transformed = [transform_geom("EPSG:4326", reference.crs, district["geometry"]) for district in districts]
            labels = rasterize(
                ((geometry, index) for index, geometry in enumerate(transformed, start=1)),
                out_shape=reliability.shape,
                transform=transform,
                fill=0,
                dtype="int16",
                all_touched=True,
            )
        with rasterio.open(signed["quality"]) as dataset:
            if (dataset.crs, dataset.transform, dataset.width, dataset.height) != reference_grid:
                raise RuntimeError(f"MOD13Q1 item {item['id']} has misaligned quality data")
            quality = dataset.read(
                1, window=window, out_shape=out_shape, masked=True, resampling=Resampling.nearest
            )
        with rasterio.open(signed["ndvi"]) as dataset:
            if (dataset.crs, dataset.transform, dataset.width, dataset.height) != reference_grid:
                raise RuntimeError(f"MOD13Q1 item {item['id']} has misaligned NDVI data")
            ndvi = dataset.read(
                1, window=window, out_shape=out_shape, masked=True, resampling=Resampling.nearest
            )
        with rasterio.open(signed["evi"]) as dataset:
            if (dataset.crs, dataset.transform, dataset.width, dataset.height) != reference_grid:
                raise RuntimeError(f"MOD13Q1 item {item['id']} has misaligned EVI data")
            evi = dataset.read(
                1, window=window, out_shape=out_shape, masked=True, resampling=Resampling.nearest
            )
    reliability_data = reliability.filled(255).astype("uint8")
    quality_data = quality.filled(65535).astype("uint16")
    ndvi_data = ndvi.filled(-3000).astype("int16")
    evi_data = evi.filled(-3000).astype("int16")
    modland = quality_data & 0b11
    good = (
        (reliability_data == 0)
        & (modland == 0)
        & (ndvi_data >= -2000)
        & (ndvi_data <= 10000)
        & (evi_data >= -2000)
        & (evi_data <= 10000)
    )
    by_district: dict[str, dict[str, Any]] = {}
    for index, district in enumerate(districts, start=1):
        inside = labels == index
        if not inside.any():
            # Recover districts fully overwritten by overlapping source features
            # (notably aggregate/admin anomalies) without paying the cost of 91
            # independent full-resolution burns for every MODIS tile.
            inside = rasterize(
                [(transformed[index - 1], 1)],
                out_shape=reliability_data.shape,
                transform=transform,
                fill=0,
                dtype="uint8",
                all_touched=True,
            ).astype(bool)
        valid = inside & good
        by_district[district["district_id"]] = {
            "inside_pixels": int(inside.sum()),
            "good_pixels": int(valid.sum()),
            "marginal_pixels": int((inside & (reliability_data == 1)).sum()),
            "cloudy_pixels": int((inside & (reliability_data == 3)).sum()),
            "ndvi_values": ndvi_data[valid].copy(),
            "evi_values": evi_data[valid].copy(),
        }
    return {
        "id": item["id"],
        "date": item["properties"].get("start_datetime", "")[:10],
        "by_district": by_district,
        "source_assets": {name: assets[key]["href"] for name, key in names.items()},
    }


def _modis_item_with_retry(
    item: dict[str, Any], districts: list[dict[str, Any]], retries: int = 3
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return _modis_item_values(item, districts)
        except Exception as error:
            last_error = error
            if attempt < retries:
                time.sleep(min(2**attempt, 10))
    raise RuntimeError(f"MOD13Q1 item {item.get('id')} failed after {retries} attempts: {last_error}")


def _collect_modis_range(
    start: date,
    end: date,
    workers: int,
    districts: list[dict[str, Any]],
    period_checkpoint_dir: Path,
) -> tuple[pd.DataFrame, list[dict[str, Any]], int]:
    """Collect one recoverable MODIS range before archive-wide derivation."""
    period_checkpoint_dir.mkdir(parents=True, exist_ok=True)
    items = modis_items(start, end)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[item["properties"]["start_datetime"][:10]].append(item)
    rows: list[dict[str, Any]] = []
    source_records: list[dict[str, Any]] = []
    for number, (period, period_items) in enumerate(sorted(grouped.items()), start=1):
        period_path = period_checkpoint_dir / f"{period}.csv"
        period_sources_path = period_checkpoint_dir / f"{period}.sources.json"
        if valid_modis_period_checkpoint(
            period_path,
            period_sources_path,
            period,
            len(districts),
            {item["id"] for item in period_items},
        ):
            rows.extend(pd.read_csv(period_path).to_dict("records"))
            source_records.extend(json.loads(period_sources_path.read_text(encoding="utf-8")))
            print(
                f"SKIP MOD13Q1 {start}/{end}: {number}/{len(grouped)} ({period})",
                flush=True,
            )
            continue
        results = []
        with ThreadPoolExecutor(max_workers=min(workers, len(period_items))) as executor:
            futures = [executor.submit(_modis_item_with_retry, item, districts) for item in period_items]
            for future in as_completed(futures):
                results.append(future.result())
        period_sources = [
            {"item_id": result["id"], "date": result["date"], "assets": result["source_assets"]}
            for result in results
        ]
        period_rows: list[dict[str, Any]] = []
        for district in districts:
            district_id = district["district_id"]
            pieces = [result["by_district"][district_id] for result in results]
            ndvi_parts = [piece["ndvi_values"] for piece in pieces if piece["ndvi_values"].size]
            evi_parts = [piece["evi_values"] for piece in pieces if piece["evi_values"].size]
            ndvi = np.concatenate(ndvi_parts).astype("float64") * 0.0001 if ndvi_parts else np.array([])
            evi = np.concatenate(evi_parts).astype("float64") * 0.0001 if evi_parts else np.array([])
            inside = sum(piece["inside_pixels"] for piece in pieces)
            good_pixels = sum(piece["good_pixels"] for piece in pieces)
            period_rows.append(
                {
                    "district_id": district_id,
                    "district_name": district["district_name"],
                    "region_id": district["region_id"],
                    "region_name": district["region_name"],
                    "date": period,
                    "ndvi_mean": float(np.mean(ndvi)) if ndvi.size else np.nan,
                    "ndvi_median": float(np.median(ndvi)) if ndvi.size else np.nan,
                    "evi_mean": float(np.mean(evi)) if evi.size else np.nan,
                    "evi_median": float(np.median(evi)) if evi.size else np.nan,
                    "valid_pixel_fraction": float(good_pixels / inside) if inside else 0.0,
                    "good_pixel_count": good_pixels,
                    "marginal_pixel_fraction": float(sum(piece["marginal_pixels"] for piece in pieces) / inside) if inside else 0.0,
                    "cloudy_pixel_fraction": float(sum(piece["cloudy_pixels"] for piece in pieces) / inside) if inside else 0.0,
                    "qa_rule": "pixel_reliability=0 AND MODLAND_QA(bits0-1)=0 AND VI range -2000..10000",
                    "source_version": "MOD13Q1 V061 Terra 250m 16-day",
                }
            )
        atomic_csv(period_path, pd.DataFrame(period_rows))
        atomic_json(period_sources_path, period_sources)
        rows.extend(period_rows)
        source_records.extend(period_sources)
        print(
            f"MOD13Q1 {start}/{end}: {number}/{len(grouped)} composite periods ({period})",
            flush=True,
        )
    frame = pd.DataFrame(rows).sort_values(["district_id", "date"])
    return frame, source_records, len(items)


def valid_modis_period_checkpoint(
    path: Path,
    sources_path: Path,
    period: str,
    district_count: int,
    expected_item_ids: set[str],
) -> bool:
    try:
        frame = pd.read_csv(path, usecols=["district_id", "date", "qa_rule"])
        sources = json.loads(sources_path.read_text(encoding="utf-8"))
        return (
            len(frame) == district_count
            and frame["district_id"].nunique() == district_count
            and frame["date"].nunique() == 1
            and str(frame["date"].iloc[0]) == period
            and not frame.duplicated(["district_id", "date"]).any()
            and bool(sources)
            and {source.get("item_id") for source in sources} == expected_item_ids
            and len({source.get("item_id") for source in sources}) == len(sources)
            and frame["qa_rule"].str.contains("pixel_reliability=0", regex=False).all()
        )
    except (OSError, ValueError, TypeError, KeyError, pd.errors.ParserError):
        return False


def valid_modis_checkpoint(
    path: Path,
    sources_path: Path,
    start: date,
    end: date,
    district_count: int,
) -> bool:
    """Accept only a complete district/composite checkpoint with source lineage."""
    try:
        frame = pd.read_csv(path, usecols=["district_id", "date", "qa_rule"])
        sources = json.loads(sources_path.read_text(encoding="utf-8"))
        periods = frame["date"].nunique()
        expected_dates = set(nominal_modis_dates(start, end))
        return (
            set(frame["date"].astype(str)) == expected_dates
            and len(frame) == periods * district_count
            and frame["district_id"].nunique() == district_count
            and not frame.duplicated(["district_id", "date"]).any()
            and frame["date"].min() >= start.isoformat()
            and frame["date"].max() <= end.isoformat()
            and len(sources) >= periods
            and len({source.get("item_id") for source in sources}) == len(sources)
            and frame["qa_rule"].str.contains("pixel_reliability=0", regex=False).all()
        )
    except (OSError, ValueError, TypeError, KeyError, pd.errors.ParserError):
        return False


def build_modis(start: date, end: date, workers: int) -> None:
    districts = load_districts()
    checkpoint_dir = PROCESSED / "vegetation" / "mod13q1_v061_district"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    year_frames: list[pd.DataFrame] = []
    source_records: list[dict[str, Any]] = []
    total_items = 0
    for year in range(start.year, end.year + 1):
        year_start = max(start, date(year, 1, 1))
        year_end = min(end, date(year, 12, 31))
        year_path = checkpoint_dir / f"mod13q1_v061_district_{year_start}_{year_end}.csv"
        sources_path = checkpoint_dir / f"mod13q1_v061_sources_{year_start}_{year_end}.json"
        if valid_modis_checkpoint(year_path, sources_path, year_start, year_end, len(districts)):
            print(f"SKIP {year_path.relative_to(ROOT)}", flush=True)
            year_frame = pd.read_csv(year_path)
            year_sources = json.loads(sources_path.read_text(encoding="utf-8"))
            year_items = len(year_sources)
        else:
            if year_path.exists() or sources_path.exists():
                print(f"REBUILD invalid MOD13Q1 checkpoint for {year_start}/{year_end}", flush=True)
            year_frame, year_sources, year_items = _collect_modis_range(
                year_start,
                year_end,
                workers,
                districts,
                checkpoint_dir / f"periods_{year_start}_{year_end}",
            )
            atomic_csv(year_path, year_frame)
            atomic_json(sources_path, year_sources)
        year_frames.append(year_frame)
        source_records.extend(year_sources)
        total_items += year_items
    frame = pd.concat(year_frames, ignore_index=True).sort_values(["district_id", "date"])
    frame["qa_summary"] = np.where(
        frame["good_pixel_count"] > 0,
        "STRICT_GOOD_PIXELS_AVAILABLE",
        "NO_STRICT_GOOD_PIXELS",
    )
    frame["date"] = pd.to_datetime(frame["date"])
    frame["year"] = frame["date"].dt.year
    frame["composite_number"] = frame.groupby("year")["date"].rank(method="dense").astype(int)
    for variable in ("ndvi", "evi"):
        baseline = frame.groupby(["district_id", "composite_number"])[f"{variable}_mean"].agg(["mean", "std"]).reset_index()
        baseline.columns = ["district_id", "composite_number", f"{variable}_baseline_mean", f"{variable}_baseline_std"]
        frame = frame.merge(baseline, on=["district_id", "composite_number"], how="left")
        frame[f"{variable}_anomaly"] = frame[f"{variable}_mean"] - frame[f"{variable}_baseline_mean"]
        frame[f"{variable}_anomaly_z"] = frame[f"{variable}_anomaly"] / frame[f"{variable}_baseline_std"].replace(0, np.nan)
    frame["vegetation_stress"] = np.clip(-frame["ndvi_anomaly_z"], 0, None)
    output = PROCESSED / "vegetation" / f"mod13q1_v061_district_{start}_{end}.csv"
    atomic_csv(output, frame)
    atomic_json(METADATA / "mod13q1_historical_sources.json", source_records)
    actual_periods = int(frame["date"].nunique())
    nominal_dates = nominal_modis_dates(start, end)
    actual_dates = set(pd.to_datetime(frame["date"]).dt.date.astype(str))
    missing_composite_dates = sorted(set(nominal_dates) - actual_dates)
    source_period_missing_fraction = (
        len(missing_composite_dates) / len(nominal_dates) if nominal_dates else 0.0
    )
    missing_fraction = float(frame["ndvi_mean"].isna().mean())
    validation = {
        "dataset": "MOD13Q1 V061 Terra district time-series",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "periods": actual_periods,
        "expected_nominal_periods": len(nominal_dates),
        "missing_composite_start_dates": missing_composite_dates,
        "source_period_missing_fraction": source_period_missing_fraction,
        "items": total_items,
        "districts": int(frame["district_id"].nunique()),
        "rows": len(frame),
        "missing_district_period_rows": int(frame["ndvi_mean"].isna().sum()),
        "missing_district_period_fraction": missing_fraction,
        "minimum_valid_pixel_fraction": float(frame["valid_pixel_fraction"].min()),
        "source_resolution": "250m",
        "derived_sampling_resolution": "approximately 1km via aligned nearest-neighbour COG overview",
        "temporal_resolution": "16-day composite",
        "scale": 0.0001,
        "fill_and_valid_ranges": {
            "NDVI": {"fill": -3000, "valid_min": -2000, "valid_max": 10000},
            "EVI": {"fill": -3000, "valid_min": -2000, "valid_max": 10000},
            "VI_Quality": {"fill": 65535, "interpretation": "bit field"},
            "pixel_reliability": {"fill": -1, "accepted": 0},
        },
        "qa_rule": frame["qa_rule"].iloc[0] if len(frame) else None,
        "sha256": sha256(output),
        "size_bytes": output.stat().st_size,
        "status": (
            "COMPLETE"
            if source_period_missing_fraction <= 0.10
            and int(frame["district_id"].nunique()) == len(districts)
            and missing_fraction <= 0.10
            else "PARTIAL"
        ),
    }
    atomic_json(METADATA / "mod13q1_historical_validation.json", validation)
    update_history_manifest(
        provider="NASA LP DAAC (Microsoft Planetary Computer host)",
        dataset="MOD13Q1 V061 district vegetation archive",
        version="061",
        source_url="https://planetarycomputer.microsoft.com/api/stac/v1/collections/modis-13Q1-061",
        path=output,
        reference_date=f"{start}/{end}",
        status=validation["status"],
    )


def update_history_manifest(
    *, provider: str, dataset: str, version: str, source_url: str, path: Path,
    reference_date: str, status: str,
) -> None:
    columns = [
        "provider", "dataset", "version", "source_url", "local_path", "reference_date",
        "downloaded_at", "size_bytes", "checksum_sha256", "status",
    ]
    rows: list[dict[str, Any]] = []
    if HISTORICAL_MANIFEST.exists():
        with HISTORICAL_MANIFEST.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
    local_path = path.relative_to(ROOT).as_posix()
    rows = [
        row
        for row in rows
        if row.get("local_path") != local_path
        and row.get("local_path")
        and (ROOT / row["local_path"]).exists()
    ]
    rows.append(
        {
            "provider": provider,
            "dataset": dataset,
            "version": version,
            "source_url": source_url,
            "local_path": local_path,
            "reference_date": reference_date,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "size_bytes": path.stat().st_size,
            "checksum_sha256": sha256(path),
            "status": status,
        }
    )
    temporary = HISTORICAL_MANIFEST.with_name(HISTORICAL_MANIFEST.name + ".part")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, HISTORICAL_MANIFEST)


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser()
    subparsers = command.add_subparsers(dest="command", required=True)
    for name in ("chirps", "modis"):
        child = subparsers.add_parser(name)
        child.add_argument("--start", required=True, help="YYYY-MM-DD")
        child.add_argument("--end", required=True, help="YYYY-MM-DD")
        child.add_argument("--workers", type=int, default=4)
    return command


def main() -> int:
    args = parser().parse_args()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if end < start:
        raise SystemExit("--end must not precede --start")
    if args.workers < 1 or args.workers > 8:
        raise SystemExit("--workers must be between 1 and 8")
    if args.command == "chirps":
        build_chirps(start, end, args.workers)
    else:
        build_modis(start, end, args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
