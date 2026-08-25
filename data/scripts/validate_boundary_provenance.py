#!/usr/bin/env python3
"""Validate embedded evidence used to match the local boundary archive to OCHA COD-AB."""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "data" / "som_admin_boundaries.geojson.zip"
PROVENANCE = ROOT / "data" / "metadata" / "boundary_provenance.json"
OUTPUT = ROOT / "data" / "metadata" / "boundary_provenance_validation.json"


def main() -> None:
    provenance = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    levels = {"ADM0": "som_admin0.geojson", "ADM1": "som_admin1.geojson", "ADM2": "som_admin2.geojson"}
    results = {}
    with zipfile.ZipFile(ARCHIVE) as archive:
        for level, member in levels.items():
            collection = json.loads(archive.read(member))
            features = collection["features"]
            versions = sorted({feature["properties"].get("version") for feature in features})
            valid_on = sorted({feature["properties"].get("valid_on") for feature in features})
            results[level] = {
                "member": member,
                "feature_count": len(features),
                "versions": versions,
                "valid_on": valid_on,
                "crs": collection.get("crs"),
            }

    checks = {
        "feature_counts_match": all(
            results[level]["feature_count"] == provenance["feature_counts"][level]
            for level in levels
        ),
        "embedded_version_match": all(
            results[level]["versions"] == [provenance["embedded_version"]] for level in levels
        ),
        "embedded_valid_on_match": all(
            results[level]["valid_on"] == [provenance["embedded_valid_on"]] for level in levels
        ),
        "official_source_is_hdx": provenance["official_dataset_url"].startswith(
            "https://data.humdata.org/dataset/"
        ),
        "local_files_not_replaced": provenance["replacement_performed"] is False,
        "unknown_download_date_preserved": provenance["download_date"] is None,
    }
    payload = {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "archive": "data/som_admin_boundaries.geojson.zip",
        "levels": results,
        "checks": checks,
        "passed": all(checks.values()),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": payload["passed"], "feature_counts": {k: v["feature_count"] for k, v in results.items()}}))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
