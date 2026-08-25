from datetime import date

import pytest

from app.modules.geography.service import (
    BoundaryValidationError,
    parse_feature,
    validate_hierarchy,
    zonal_statistics,
)
from app.modules.ingestion.csv_adapter import parse_observation_csv
from app.modules.seasons.service import SeasonWindow, season_for


def feature(code: str, level: str, parent: str | None = None) -> dict[str, object]:
    return {
        "type": "Feature",
        "properties": {
            "stable_code": code,
            "name": code,
            "level": level,
            "parent_code": parent,
            "aliases": [],
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[45, 5], [46, 5], [46, 6], [45, 6], [45, 5]]],
        },
    }


def test_boundary_version_and_hierarchy_are_explicit() -> None:
    country = parse_feature(
        feature("SO", "country"),
        version="test-v1",
        source="SYNTHETIC / DEVELOPMENT DATA",
        valid_from=date(2020, 1, 1),
    )
    region = parse_feature(
        feature("SO-R1", "region", "SO"),
        version="test-v1",
        source="SYNTHETIC / DEVELOPMENT DATA",
        valid_from=date(2020, 1, 1),
    )
    validate_hierarchy([country, region])
    with pytest.raises(BoundaryValidationError):
        validate_hierarchy([region])


def test_zonal_statistics_preserve_missing_cells_and_reject_ragged_grids() -> None:
    geometry = feature("SO-D1", "district", "SO-R1")["geometry"]
    assert isinstance(geometry, dict)
    result = zonal_statistics(
        geometry,
        [[10, None], [30, 50]],
        west=45,
        south=5,
        east=46,
        north=6,
    )
    assert result == {
        "cells_in_zone": 4,
        "valid_cells": 3,
        "missing_cells": 1,
        "coverage": 0.75,
        "minimum": 10,
        "maximum": 50,
        "mean": 30,
    }
    with pytest.raises(BoundaryValidationError, match="rectangular"):
        zonal_statistics(geometry, [[1], [2, 3]], west=45, south=5, east=46, north=6)


def test_file_ingestion_preserves_missing_and_quarantines_duplicates() -> None:
    result = parse_observation_csv(
        "source_record_id,admin_unit_code,indicator_code,value,unit,reference_time\na,SO-R1,rainfall,,mm,2026-01-01T00:00:00Z\na,SO-R1,rainfall,0,mm,2026-01-02T00:00:00Z\n"
    )
    assert result.accepted[0].value is None
    assert len(result.rejected) == 1
    assert "duplicate" in result.rejected[0].reason


def test_seasons_are_configured_not_hardcoded() -> None:
    gu = SeasonWindow("Gu", date(2026, 4, 1), date(2026, 6, 30), "approved-test-guidance", "v1")
    assert season_for(date(2026, 5, 1), [gu]) == gu
    assert season_for(date(2026, 8, 1), [gu]) is None
