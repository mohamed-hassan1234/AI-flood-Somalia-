from dataclasses import dataclass
from datetime import date
from typing import Any

from shapely import Point
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry


class BoundaryValidationError(ValueError):
    pass


def governed_geometry(value: dict[str, Any]) -> BaseGeometry:
    try:
        geometry = shape(value)
    except (TypeError, ValueError) as exc:
        raise BoundaryValidationError("Boundary geometry is not valid GeoJSON") from exc
    if geometry.is_empty or not geometry.is_valid:
        raise BoundaryValidationError("Boundary geometry must be non-empty and topologically valid")
    return geometry


@dataclass(frozen=True)
class BoundaryFeature:
    stable_code: str
    name: str
    level: str
    parent_code: str | None
    version: str
    source: str
    valid_from: date
    aliases: tuple[str, ...]
    geometry: dict[str, Any]


def parse_feature(
    feature: dict[str, Any], *, version: str, source: str, valid_from: date
) -> BoundaryFeature:
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    required = {"stable_code", "name", "level"}
    missing = sorted(required - properties.keys())
    if missing:
        raise BoundaryValidationError(f"Missing boundary properties: {', '.join(missing)}")
    if properties["level"] not in {"country", "region", "district"}:
        raise BoundaryValidationError("Unsupported administrative level")
    if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise BoundaryValidationError("Boundaries must use Polygon or MultiPolygon geometry")
    governed_geometry(geometry)
    aliases = properties.get("aliases", [])
    if not isinstance(aliases, list) or not all(isinstance(item, str) for item in aliases):
        raise BoundaryValidationError("Aliases must be an explicit list of names")
    return BoundaryFeature(
        str(properties["stable_code"]),
        str(properties["name"]),
        str(properties["level"]),
        properties.get("parent_code"),
        version,
        source,
        valid_from,
        tuple(aliases),
        geometry,
    )


def validate_hierarchy(features: list[BoundaryFeature]) -> None:
    codes = {feature.stable_code for feature in features}
    for feature in features:
        if feature.level != "country" and (
            feature.parent_code is None or feature.parent_code not in codes
        ):
            raise BoundaryValidationError(f"Missing explicit parent for {feature.stable_code}")


def contains_point(geometry: dict[str, Any], longitude: float, latitude: float) -> bool:
    return governed_geometry(geometry).covers(Point(longitude, latitude))


def zonal_statistics(
    geometry: dict[str, Any],
    values: list[list[float | None]],
    *,
    west: float,
    south: float,
    east: float,
    north: float,
) -> dict[str, float | int | None]:
    if east <= west or north <= south:
        raise BoundaryValidationError("Raster extent must have east > west and north > south")
    width = len(values[0])
    if width == 0 or width > 512 or any(len(row) != width for row in values):
        raise BoundaryValidationError("Raster grid must be rectangular and at most 512 columns")
    zone = governed_geometry(geometry)
    x_size = (east - west) / width
    y_size = (north - south) / len(values)
    in_zone: list[float | None] = []
    for row_index, row in enumerate(values):
        latitude = north - (row_index + 0.5) * y_size
        for column_index, value in enumerate(row):
            longitude = west + (column_index + 0.5) * x_size
            if zone.covers(Point(longitude, latitude)):
                in_zone.append(value)
    valid = [value for value in in_zone if value is not None]
    return {
        "cells_in_zone": len(in_zone),
        "valid_cells": len(valid),
        "missing_cells": len(in_zone) - len(valid),
        "coverage": len(valid) / len(in_zone) if in_zone else 0.0,
        "minimum": min(valid) if valid else None,
        "maximum": max(valid) if valid else None,
        "mean": sum(valid) / len(valid) if valid else None,
    }
