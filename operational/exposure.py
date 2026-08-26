"""P3-01 exposure analysis.

Combines validated Phase 02 risk outputs with the Phase 01 WorldPop-derived
population tables. Every function returns a clearly labeled, honestly scoped
exposure record: ``population_context`` is always the population of the
relevant geography (known), while ``population_potentially_exposed`` is only
populated when a defensible exposure geometry exists for that risk type.

Flood carries no validated inundation/exposure geometry in Phase 01/02, so
its ``population_potentially_exposed`` is always ``None`` -- a scientifically
honest null, never a fabricated buffer or city-population substitute.
"""

from __future__ import annotations

from typing import Any

from operational.geography import registry

NORMAL = "NORMAL"


def drought_exposure(district_id: str, risk_level: str) -> dict[str, Any]:
    district = registry().district(district_id)
    at_risk = risk_level != NORMAL
    return {
        "scope_type": "DISTRICT",
        "population_context": district.population,
        "population_potentially_exposed": district.population if at_risk else 0.0,
        "exposure_method": (
            "full_canonical_district_population_at_or_above_watch_threshold"
            if at_risk
            else "no_exposure_claim_at_normal_risk_level"
        ),
        "exposure_uncertainty": (
            "Whole-district approximation: the drought target is a district-level agricultural/vegetation "
            "signal, not a sub-district exposure geometry. No cropland/settlement mask was available in "
            "Phase 01, so the entire district population is reported as potentially exposed, not confirmed "
            "affected."
        ),
        "population_source": district.population_source,
        "population_year": district.population_year,
    }


def flood_exposure(station_code: str, risk_level: str) -> dict[str, Any]:
    district = registry().station_linked_district(station_code)
    return {
        "scope_type": "STATION",
        "population_context": district.population,
        "population_potentially_exposed": None,
        "exposure_method": "station_operational_context_only_no_validated_inundation_geometry",
        "exposure_uncertainty": (
            "No floodplain, river-corridor, or historical inundation footprint exists in the Phase 01 data "
            "foundation. population_context is the population of the district nearest the gauge "
            f"({district.district_id} — {district.district_name}), reported for operational orientation "
            "only. It must never be read as an exposed-population or affected-population estimate; the "
            "true flood-exposed population is unknown without validated inundation geometry."
        ),
        "population_source": district.population_source,
        "population_year": district.population_year,
        "linked_district_id": district.district_id,
        "linked_district_name": district.district_name,
        "risk_level": risk_level,
    }


def food_security_exposure(region_id: str, risk_level: str) -> dict[str, Any]:
    region = registry().region(region_id)
    return {
        "scope_type": "REGION",
        "population_context": region.population,
        "population_potentially_exposed": None,
        "exposure_method": "model_predicts_binary_burden_threshold_not_a_population_fraction",
        "exposure_uncertainty": (
            "The food-security target predicts whether the observed regional Crisis-or-worse population "
            "share will reach 20%, not the exact share itself. Reporting a specific exposed-population "
            "number from a binary threshold prediction would fabricate precision the model does not have. "
            "population_context is the total regional population for orientation only; it is not an "
            "estimate of the number of food-insecure people."
        ),
        "population_source": region.population_source,
        "population_year": region.population_year,
        "risk_level": risk_level,
    }


def observed_historical_population_in_phase3plus(region_id: str, previous_ipc3plus_percentage: float | None) -> float | None:
    """Historical-context-only figure for replay/backtesting narratives.

    Derived from an *observed* prior IPC Phase 3+ percentage, never from a model
    prediction. Used only in the operational replay report to describe what was
    actually known/observed, never attached to a live prediction record.
    """
    if previous_ipc3plus_percentage is None:
        return None
    region = registry().region(region_id)
    return float(region.population) * float(previous_ipc3plus_percentage)
