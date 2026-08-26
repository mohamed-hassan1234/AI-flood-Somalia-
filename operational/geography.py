"""Canonical operational geography layer for Phase 03.

Reuses Phase 01 population outputs and the geography already resolved inside
the frozen Phase 02 model-ready datasets (district/region ids and names,
station-to-district-to-river mapping). No geometry is invented here and no
name is heuristically remapped when a canonical id already exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MODEL_READY = DATA / "model_ready"
POPULATION = DATA / "processed" / "population"


class UnsupportedGeographyError(ValueError):
    """Raised when a geography id/code is outside the validated Phase 02 model scope."""


@dataclass(frozen=True)
class District:
    district_id: str
    district_name: str
    region_id: str
    region_name: str
    population: float
    population_source: str
    population_year: int


@dataclass(frozen=True)
class Region:
    region_id: str
    region_name: str
    population: float
    population_source: str
    population_year: int


@dataclass(frozen=True)
class Station:
    station_code: str
    district_id: str
    river: str
    moderate_threshold_m: float
    high_threshold_m: float
    bankfull_threshold_m: float


def _population_source_label() -> str:
    return "worldpop_derived_phase01_population_summary"


class GeographyRegistry:
    """Loads once, then serves district/region/station lookups with explicit scope errors."""

    def __init__(self) -> None:
        district_pop = pd.read_csv(POPULATION / "district_population_2025.csv")
        region_pop = pd.read_csv(POPULATION / "region_population_2025.csv")
        self.population_year = int(district_pop["reference_year"].iloc[0])

        self._districts: dict[str, District] = {
            row.canonical_district_id: District(
                district_id=row.canonical_district_id,
                district_name=row.canonical_district_name,
                region_id=row.canonical_region_id,
                region_name=row.canonical_region_name,
                population=float(row.district_population),
                population_source=_population_source_label(),
                population_year=int(row.reference_year),
            )
            for row in district_pop.itertuples()
        }
        self._regions: dict[str, Region] = {
            row.canonical_region_id: Region(
                region_id=row.canonical_region_id,
                region_name=row.canonical_region_name,
                population=float(row.region_population),
                population_source=_population_source_label(),
                population_year=int(row.reference_year),
            )
            for row in region_pop.itertuples()
        }

        flood = pd.read_csv(
            MODEL_READY / "flood" / "flood_dataset_v1.1.0.csv.gz",
            usecols=["station_code", "canonical_district_id", "river", "moderate_threshold_m", "high_threshold_m", "bankfull_threshold_m"],
        )
        station_rows = flood.sort_values("feature_as_of_date" if "feature_as_of_date" in flood else "station_code").drop_duplicates("station_code", keep="last")
        self._stations: dict[str, Station] = {
            row.station_code: Station(
                station_code=row.station_code,
                district_id=row.canonical_district_id,
                river=row.river,
                moderate_threshold_m=float(row.moderate_threshold_m),
                high_threshold_m=float(row.high_threshold_m),
                bankfull_threshold_m=float(row.bankfull_threshold_m),
            )
            for row in station_rows.itertuples()
        }

        drought_geo = pd.read_csv(
            MODEL_READY / "drought" / "drought_dataset_v1.1.0.csv.gz",
            usecols=["district_id"],
        )
        self.drought_supported_districts: frozenset[str] = frozenset(drought_geo.district_id.dropna().unique())

        fs_geo = pd.read_csv(
            MODEL_READY / "food_security" / "food_security_dataset_v1.1.0.csv.gz",
            usecols=["region_id"],
        )
        self.food_security_supported_regions: frozenset[str] = frozenset(fs_geo.region_id.dropna().unique())
        self.flood_supported_stations: frozenset[str] = frozenset(self._stations.keys())

    def district(self, district_id: str) -> District:
        if district_id == "Unspecified":
            raise UnsupportedGeographyError(
                "district_id 'Unspecified' is a Phase 01 unresolved-observation bucket, not a real, "
                "mappable district; it must never be surfaced as an operational geography unit"
            )
        if district_id not in self._districts:
            raise UnsupportedGeographyError(f"Unknown district_id '{district_id}': not present in the Phase 01 canonical district population table")
        if district_id not in self.drought_supported_districts:
            raise UnsupportedGeographyError(f"District '{district_id}' has no validated Phase 02 drought model coverage")
        return self._districts[district_id]

    def region(self, region_id: str) -> Region:
        if region_id not in self._regions:
            raise UnsupportedGeographyError(f"Unknown region_id '{region_id}': not present in the Phase 01 canonical region population table")
        if region_id not in self.food_security_supported_regions:
            raise UnsupportedGeographyError(f"Region '{region_id}' has no validated Phase 02 food-security model coverage")
        return self._regions[region_id]

    def station(self, station_code: str) -> Station:
        if station_code not in self._stations:
            raise UnsupportedGeographyError(
                f"Station '{station_code}' is not one of the five Phase 02 validated riverine gauges "
                f"({sorted(self.flood_supported_stations)}); no riverine flood prediction exists for it"
            )
        return self._stations[station_code]

    def station_linked_district(self, station_code: str) -> District:
        station = self.station(station_code)
        return self._districts[station.district_id]


_REGISTRY: GeographyRegistry | None = None


def registry() -> GeographyRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = GeographyRegistry()
    return _REGISTRY
