"""Reproducible Phase 01 source connectors.

Downloads are idempotent and atomic: bytes are written to ``.part`` first and
renamed only after a successful response. Source URLs, sizes, and SHA-256 values
are persisted in data/metadata/download_manifest.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
METADATA = ROOT / "metadata"
MANIFEST = METADATA / "download_manifest.json"
USER_AGENT = "Somalia-AI-Phase01/1.0 (governed research connector)"

HDX_MARKET = {
    "wfp_food_prices_som.csv": "https://data.humdata.org/dataset/26727d1b-af49-4323-9215-c2ac479abb87/resource/39614bfb-0f9c-4800-8997-e68e41a38ced/download/wfp_food_prices_som.csv",
    "wfp_markets_som.csv": "https://data.humdata.org/dataset/26727d1b-af49-4323-9215-c2ac479abb87/resource/bf3725e2-cbb5-4dc2-8d6a-2f2f1c6ef855/download/wfp_markets_som.csv",
}
HDX_IPC = {
    "ipc_som.geojson": "https://data.humdata.org/dataset/26cac16a-98cd-4c4e-9353-40bd423302c0/resource/1c8d0767-78cb-422f-96ee-fe3aa7299e1e/download/ipc_som.geojson",
    "ipc_som_national_long.csv": "https://data.humdata.org/dataset/26cac16a-98cd-4c4e-9353-40bd423302c0/resource/0205b347-e64b-4987-bd70-38f8edff452b/download/ipc_som_national_long.csv",
    "ipc_som_level1_long.csv": "https://data.humdata.org/dataset/26cac16a-98cd-4c4e-9353-40bd423302c0/resource/fa87ad6b-d8f8-41d7-9f86-f6b46a434fdf/download/ipc_som_level1_long.csv",
    "ipc_som_area_long.csv": "https://data.humdata.org/dataset/26cac16a-98cd-4c4e-9353-40bd423302c0/resource/80be59cd-6d1d-423f-9114-e2fb507fd257/download/ipc_som_area_long.csv",
}
WORLDPOP_2025 = {
    "som_pop_2025_CN_100m_R2025A_v1.tif": "https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2025/SOM/v1/100m/constrained/som_pop_2025_CN_100m_R2025A_v1.tif"
}
MODIS = {
    "vegetation": {
        "collection": "modis-13Q1-061",
        "assets": [
            "250m_16_days_NDVI",
            "250m_16_days_EVI",
            "250m_16_days_VI_Quality",
            "250m_16_days_pixel_reliability",
        ],
    },
    "temperature": {
        "collection": "modis-11A1-061",
        "assets": ["LST_Day_1km", "QC_Day", "LST_Night_1km", "QC_Night"],
    },
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def read_manifest() -> dict[str, Any]:
    if not MANIFEST.exists():
        return {"schema_version": 1, "downloads": {}}
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def save_manifest(manifest: dict[str, Any]) -> None:
    METADATA.mkdir(parents=True, exist_ok=True)
    temporary = MANIFEST.with_suffix(".json.part")
    temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, MANIFEST)


def request_json(url: str, *, payload: dict[str, Any] | None = None, timeout: int = 120) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": USER_AGENT, **({"Content-Type": "application/json"} if data else {})},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def download_atomic(
    url: str,
    destination: Path,
    *,
    retries: int = 3,
    timeout: int = 300,
    manifest_url: str | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        print(f"SKIP existing {destination.relative_to(ROOT)}")
        register_download(manifest_url or url, destination, "existing")
        return destination
    partial = destination.with_name(destination.name + ".part")
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response, partial.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
            if partial.stat().st_size == 0:
                raise RuntimeError("provider returned an empty file")
            os.replace(partial, destination)
            register_download(manifest_url or url, destination, "downloaded")
            print(f"OK {destination.relative_to(ROOT)} ({destination.stat().st_size} bytes)")
            return destination
        except (OSError, RuntimeError, urllib.error.URLError) as exc:
            last_error = exc
            if partial.exists():
                partial.unlink()
            if attempt < retries:
                time.sleep(min(2**attempt, 10))
    raise RuntimeError(f"Failed after {retries} attempts: {url}: {last_error}")


def register_download(url: str, path: Path, disposition: str) -> None:
    manifest = read_manifest()
    key = path.relative_to(ROOT).as_posix()
    manifest["downloads"][key] = {
        "source_url": url,
        "size_bytes": path.stat().st_size,
        "sha256": digest(path),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "disposition": disposition,
    }
    save_manifest(manifest)


def fixed_downloads(files: dict[str, str], family: str) -> None:
    for filename, url in files.items():
        download_atomic(url, RAW / family / filename)


def chirps_daily_final_rnl(start: str, end: str, max_files: int) -> None:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    if end_date < start_date:
        raise ValueError("--end must not be earlier than --start")
    days = (end_date - start_date).days + 1
    if max_files < 1 or days > max_files:
        raise ValueError(
            f"Requested {days} daily files; increase --max-files from {max_files} after estimating storage"
        )
    current = start_date
    while current <= end_date:
        filename = f"chirps-v3.0.rnl.{current:%Y.%m.%d}.tif"
        url = (
            "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/"
            f"{current:%Y}/{filename}"
        )
        download_atomic(url, RAW / "rainfall" / "chirps_v3_daily_final_rnl" / f"{current:%Y}" / filename, timeout=900)
        current += timedelta(days=1)


def nasa_power(
    start: str,
    end: str,
    parameters: list[str],
    bbox: tuple[float, float, float, float],
) -> None:
    south, west, north, east = bbox
    # POWER rejects oversized regional requests. Tile the requested extent at
    # <=10 degrees and keep the tile number in deterministic filenames.
    tiles: list[tuple[float, float, float, float]] = []
    latitude_parts = max(1, math.ceil((north - south) / 10.0))
    longitude_parts = max(1, math.ceil((east - west) / 10.0))
    latitude_step = (north - south) / latitude_parts
    longitude_step = (east - west) / longitude_parts
    for latitude_index in range(latitude_parts):
        tile_south = south + latitude_index * latitude_step
        tile_north = north if latitude_index == latitude_parts - 1 else tile_south + latitude_step
        for longitude_index in range(longitude_parts):
            tile_west = west + longitude_index * longitude_step
            tile_east = east if longitude_index == longitude_parts - 1 else tile_west + longitude_step
            tiles.append((tile_south, tile_west, tile_north, tile_east))
    for parameter in parameters:
        for tile_number, (tile_south, tile_west, tile_north, tile_east) in enumerate(tiles, start=1):
            query = urllib.parse.urlencode(
                {
                    "latitude-min": tile_south,
                    "latitude-max": tile_north,
                    "longitude-min": tile_west,
                    "longitude-max": tile_east,
                    "parameters": parameter,
                    "community": "AG",
                    "start": start,
                    "end": end,
                    "format": "CSV",
                    "time-standard": "UTC",
                }
            )
            url = f"https://power.larc.nasa.gov/api/temporal/daily/regional?{query}"
            bounds_label = "_".join(
                f"{coordinate:.3f}".replace("-", "m").replace(".", "p")
                for coordinate in (tile_south, tile_west, tile_north, tile_east)
            )
            filename = (
                f"nasa_power_daily_{parameter.lower()}_{start}_{end}_somalia_"
                f"tile{tile_number:02d}_{bounds_label}.csv"
            )
            download_atomic(url, RAW / "temperature" / "nasa_power" / filename, timeout=600)


def _sign_planetary_computer_url(href: str) -> str:
    endpoint = "https://planetarycomputer.microsoft.com/api/sas/v1/sign?" + urllib.parse.urlencode(
        {"href": href}
    )
    signed = request_json(endpoint)
    if not isinstance(signed, dict) or not isinstance(signed.get("href"), str):
        raise RuntimeError("Planetary Computer did not return a signed asset URL")
    return signed["href"]


def modis_stac(
    family: str,
    start: str,
    end: str,
    bbox: tuple[float, float, float, float],
    max_items: int,
) -> None:
    config = MODIS[family]
    west, south, east, north = bbox
    payload = {
        "collections": [config["collection"]],
        "bbox": [west, south, east, north],
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
        "limit": 100,
    }
    response = request_json(
        "https://planetarycomputer.microsoft.com/api/stac/v1/search", payload=payload
    )
    features = sorted(
        (
            item
            for item in response.get("features", [])
            if item.get("properties", {}).get("platform") == "terra"
        ),
        key=lambda item: item.get("id", ""),
    )
    if not features:
        raise RuntimeError("No MODIS STAC items matched the requested space/time range")
    selected = features[:max_items]
    metadata_dir = METADATA / "stac" / family
    metadata_dir.mkdir(parents=True, exist_ok=True)
    search_path = metadata_dir / f"search_{start}_{end}.json"
    search_path.write_text(json.dumps(response, indent=2) + "\n", encoding="utf-8")
    for item in selected:
        item_id = item["id"]
        item_path = metadata_dir / f"{item_id}.json"
        item_path.write_text(json.dumps(item, indent=2) + "\n", encoding="utf-8")
        assets = item.get("assets", {})
        for asset_name in config["assets"]:
            asset = assets.get(asset_name)
            if not asset or not asset.get("href"):
                raise RuntimeError(f"{item_id} has no {asset_name} asset")
            signed_url = _sign_planetary_computer_url(asset["href"])
            extension = ".tif" if "tiff" in str(asset.get("type", "")) else Path(asset["href"]).suffix
            filename = f"{item_id}__{asset_name}{extension}"
            download_atomic(
                signed_url,
                RAW / family / "modis_v061_sample" / filename,
                timeout=900,
                manifest_url=asset["href"],
            )


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser()
    subparsers = command.add_subparsers(dest="command", required=True)
    chirps = subparsers.add_parser("chirps")
    chirps.add_argument("--start", required=True, help="YYYY-MM-DD")
    chirps.add_argument("--end", required=True, help="YYYY-MM-DD")
    chirps.add_argument("--max-files", type=int, default=31)
    subparsers.add_parser("market")
    subparsers.add_parser("ipc")
    subparsers.add_parser("population")

    power = subparsers.add_parser("nasa-power")
    power.add_argument("--start", default="20250101")
    power.add_argument("--end", default="20251231")
    power.add_argument("--parameters", nargs="+", default=["T2M", "T2M_MAX", "T2M_MIN"])
    power.add_argument("--bbox", nargs=4, type=float, default=[-2.0, 41.0, 12.5, 52.0], metavar=("S", "W", "N", "E"))

    modis = subparsers.add_parser("modis")
    modis.add_argument("family", choices=sorted(MODIS))
    modis.add_argument("--start", required=True, help="YYYY-MM-DD")
    modis.add_argument("--end", required=True, help="YYYY-MM-DD")
    modis.add_argument("--bbox", nargs=4, type=float, default=[41.0, -2.0, 52.0, 12.5], metavar=("W", "S", "E", "N"))
    modis.add_argument("--max-items", type=int, default=1)
    return command


def main() -> int:
    args = parser().parse_args()
    if args.command == "chirps":
        chirps_daily_final_rnl(args.start, args.end, args.max_files)
    elif args.command == "market":
        fixed_downloads(HDX_MARKET, "market_prices")
    elif args.command == "ipc":
        fixed_downloads(HDX_IPC, "food_security")
    elif args.command == "population":
        fixed_downloads(WORLDPOP_2025, "population")
    elif args.command == "nasa-power":
        nasa_power(args.start, args.end, args.parameters, tuple(args.bbox))
    elif args.command == "modis":
        if args.max_items < 1 or args.max_items > 100:
            raise SystemExit("--max-items must be between 1 and 100")
        modis_stac(args.family, args.start, args.end, tuple(args.bbox), args.max_items)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
