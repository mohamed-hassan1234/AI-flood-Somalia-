"""P3-03 risk -> impact intelligence record assembly.

Builds the single stable operational-intelligence schema shared across all
three risk types (Rule 15). Every field that cannot be scientifically
supported for a given row is explicitly null rather than guessed.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from ml.common import ModelBundle, finite_or_none, now, sha256
from operational import actions as actions_module
from operational import exposure as exposure_module
from operational import warning as warning_module
from operational.drivers import local_drivers, reason_codes as reason_codes_from_drivers
from operational.geography import registry

ROOT = Path(__file__).resolve().parents[1]
ML_ARTIFACTS = ROOT / "ml" / "artifacts"
PIPELINE_VERSION = "1.0.0"

PREDICTION_HORIZON_DAYS = {"drought": 16, "flood": 3, "food_security": 30}
PREDICTION_HORIZON_LABEL = {
    "drought": "next MOD13Q1 16-day composite",
    "flood": "1-3 days",
    "food_security": "30 days pre-assessment",
}

LIMITATIONS = {
    "drought": [
        "Predicts environmental/agricultural vegetation stress, not humanitarian food insecurity directly.",
        "District-level unit; no sub-district exposure geometry is available.",
    ],
    "flood": [
        "Riverine early warning for five supported Jubba/Shabelle gauges only; not Somalia-wide, not flash/surface flood.",
        "No validated inundation geometry exists; population_context is district orientation only, not exposed population.",
    ],
    "food_security": [
        "Region-level (IPC Level 1) signal; not a district-level food-security classification.",
        "Predicts a binary Crisis-or-worse burden threshold, not an exact affected-population count.",
        "Small sample size; calibration intentionally left uncalibrated due to a validation prevalence shift.",
    ],
}


class ModelChecksumError(RuntimeError):
    """Raised when a loaded model artifact does not match its recorded checksum -- fail safe, never silently retrain."""


def load_verified_bundle(track: str) -> tuple[ModelBundle, dict[str, Any]]:
    metadata = json.loads((ML_ARTIFACTS / track / "model_metadata.json").read_text(encoding="utf-8"))
    artifact_path = ROOT / metadata["artifact_path"]
    actual_checksum = sha256(artifact_path)
    if actual_checksum != metadata["artifact_checksum_sha256"]:
        raise ModelChecksumError(
            f"{track} model artifact checksum mismatch: expected {metadata['artifact_checksum_sha256']}, got {actual_checksum}. "
            "Refusing to run inference with an unverified artifact."
        )
    bundle: ModelBundle = joblib.load(artifact_path)
    return bundle, metadata


def _condition_label(value: float | None, median: float, low_q: float, high_q: float) -> str:
    if value is None or pd.isna(value):
        return "unknown"
    if value <= low_q:
        return "much below normal"
    if value < median:
        return "below normal"
    if value >= high_q:
        return "much above normal"
    if value > median:
        return "above normal"
    return "near normal"


def _cond(bundle: ModelBundle, row: pd.Series, feature: str) -> str:
    if feature not in bundle.feature_names:
        return "unavailable"
    low, high = bundle.training_ranges[feature]
    return _condition_label(row.get(feature), bundle.training_medians[feature], low, high)


def impact_summary(track: str, row: pd.Series, bundle: ModelBundle, risk_level: str) -> dict[str, Any]:
    if track == "drought":
        return {
            "signal": "AGRICULTURAL_VEGETATION_STRESS",
            "vegetation_stress": _cond(bundle, row, "ndvi_last_anomaly_z_reference"),
            "vegetation_trend": _cond(bundle, row, "ndvi_change_1"),
            "rainfall_condition_30d": _cond(bundle, row, "rain_30d_mm"),
            "soil_wetness_condition": _cond(bundle, row, "gwet_top_30d"),
            "temperature_condition_30d": _cond(bundle, row, "t2m_30d_c"),
        }
    if track == "flood":
        return {
            "signal": "RIVERINE_THRESHOLD_EXCEEDANCE",
            "station": row.get("station_code"),
            "river": row.get("river"),
            "level_condition": _cond(bundle, row, "level_ratio_moderate"),
            "rate_of_rise_3d": _cond(bundle, row, "level_change_3d"),
            "antecedent_rainfall_7d": _cond(bundle, row, "rain_7d_mm"),
            "antecedent_soil_wetness": _cond(bundle, row, "gwet_top_7d"),
        }
    return {
        "signal": "CRISIS_OR_WORSE_BURDEN_RISK",
        "prediction_unit": "REGION",
        "market_stress": _cond(bundle, row, "market_price_anomaly_365d"),
        "climate_context_rainfall_30d": _cond(bundle, row, "rain_30d_mm"),
        "vegetation_context": _cond(bundle, row, "ndvi_last"),
        "previous_ipc_context": _cond(bundle, row, "previous_ipc3plus_percentage"),
    }


def _geography_block(track: str, row: pd.Series) -> dict[str, Any]:
    reg = registry()
    if track == "drought":
        district = reg.district(row["district_id"])
        return {"type": "DISTRICT", "id": district.district_id, "name": district.district_name, "parent_region_id": district.region_id}
    if track == "flood":
        station = reg.station(row["station_code"])
        district = reg.station_linked_district(row["station_code"])
        return {"type": "STATION", "id": station.station_code, "name": f"{station.station_code} ({district.district_name})", "parent_region_id": district.region_id}
    region = reg.region(row["region_id"])
    return {"type": "REGION", "id": region.region_id, "name": region.region_name, "parent_region_id": None}


def _exposure_block(track: str, row: pd.Series, risk_level: str) -> dict[str, Any]:
    if track == "drought":
        return exposure_module.drought_exposure(row["district_id"], risk_level)
    if track == "flood":
        return exposure_module.flood_exposure(row["station_code"], risk_level)
    return exposure_module.food_security_exposure(row["region_id"], risk_level)


def intelligence_id(track: str, geography_id: str, as_of_date: str, model_version: str, dataset_checksum: str) -> str:
    payload = f"{track}|{geography_id}|{as_of_date}|{model_version}|{dataset_checksum}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def build_record(
    track: str,
    row: pd.Series,
    bundle: ModelBundle,
    model_metadata: dict[str, Any],
    dataset_meta: dict[str, Any],
    include_drivers: bool = True,
) -> dict[str, Any]:
    """Assemble one full operational intelligence record.

    ``include_drivers=False`` skips the per-feature median-perturbation pass
    (the expensive step) for high-volume batch use such as historical replay
    over thousands of rows; every other pipeline stage still runs. The live
    operational pipeline always computes drivers.
    """
    as_of_date = pd.Timestamp(row["feature_as_of_date"])
    frame = pd.DataFrame([row[bundle.feature_names]])
    prediction = bundle.predict(frame)[0]
    risk_level = prediction["risk_level"] if prediction["data_quality"] != "INSUFFICIENT" else "UNKNOWN"

    geography = _geography_block(track, row)
    drivers = (
        local_drivers(bundle, row, track)
        if include_drivers and prediction["data_quality"] != "INSUFFICIENT"
        else []
    )
    codes = reason_codes_from_drivers(drivers)

    freshness = warning_module.freshness_assessment(track, row, as_of_date)
    overall_quality = warning_module.combined_data_quality(prediction["data_quality"], freshness["status"])
    effective_risk_level = risk_level if risk_level != "UNKNOWN" else "NORMAL"
    warning = warning_module.warning_decision(effective_risk_level, prediction["data_quality"], freshness["status"], overall_quality)

    exposure = _exposure_block(track, row, effective_risk_level) if overall_quality != "INSUFFICIENT" else {
        "scope_type": {"drought": "DISTRICT", "flood": "STATION", "food_security": "REGION"}[track],
        "population_context": None, "population_potentially_exposed": None,
        "exposure_method": "withheld_insufficient_data_quality", "exposure_uncertainty": "not computed: INSUFFICIENT data quality",
        "population_source": None, "population_year": None,
    }

    recommended = actions_module.recommended_actions(track, effective_risk_level, codes) if warning["eligible"] else []

    horizon_days = PREDICTION_HORIZON_DAYS[track]
    record = {
        "intelligence_id": intelligence_id(track, geography["id"], as_of_date.date().isoformat(), bundle.version, dataset_meta["sha256"]),
        "risk_type": track.upper(),
        "as_of_date": as_of_date.date().isoformat(),
        "valid_from": (as_of_date + timedelta(days=1)).date().isoformat(),
        "valid_until": (as_of_date + timedelta(days=horizon_days)).date().isoformat(),
        "prediction_horizon": PREDICTION_HORIZON_LABEL[track],
        "geography": geography,
        "station_code": row.get("station_code") if track == "flood" else None,
        "river_name": row.get("river") if track == "flood" else None,
        "prediction": {
            "probability": prediction["probability"],
            "risk_level": risk_level,
            "threshold_version": bundle.version,
            "risk_thresholds": bundle.risk_thresholds,
        },
        "exposure": exposure,
        "impact_summary": impact_summary(track, row, bundle, effective_risk_level) if overall_quality != "INSUFFICIENT" else None,
        "drivers": drivers,
        "warning": {
            **warning,
            "reason_codes": codes,
        },
        "recommended_actions": recommended,
        "data_quality": {
            "model_input_quality": prediction["data_quality"],
            "feature_availability": prediction["feature_availability"],
            "out_of_range_features": prediction["out_of_range_features"],
            "freshness": freshness,
            "overall_status": overall_quality,
        },
        "model": {
            "id": model_metadata["model_id"],
            "version": model_metadata["model_version"],
            "algorithm": model_metadata["algorithm"],
            "calibration_method": model_metadata["calibration_method"],
        },
        "lineage": {
            "dataset_version": dataset_meta["dataset_version"],
            "dataset_checksum_sha256": dataset_meta["sha256"],
            "feature_version": model_metadata["feature_version"],
            "target_version": model_metadata["target_version"],
            "threshold_version": model_metadata["model_version"],
            "action_catalogue_version": actions_module.CATALOG_VERSION,
            "pipeline_version": PIPELINE_VERSION,
            "as_of_date": as_of_date.date().isoformat(),
        },
        "limitations": LIMITATIONS[track],
        "generated_at": now(),
    }
    return finite_or_none(record)
