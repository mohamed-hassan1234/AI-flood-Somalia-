"""Per-prediction driver extraction and structured warning reason codes.

Reuses the same model-agnostic median-perturbation approach Phase 02 used for
local explanations (``ml.common.global_and_local_explanations``), applied to
one operational row at a time, then maps the top drivers onto a fixed,
evidence-backed reason-code vocabulary. No reason code is emitted unless the
underlying feature actually moved the prediction.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ml.common import ModelBundle

# Feature -> (reason_code, direction that supports the code: "high" or "low")
REASON_CODE_MAP: dict[str, dict[str, tuple[str, str]]] = {
    "drought": {
        "ndvi_last_anomaly_z_reference": ("LOW_NDVI_ANOMALY", "low"),
        "ndvi_change_1": ("HIGH_VEGETATION_STRESS_RISK", "low"),
        "ndvi_last": ("HIGH_VEGETATION_STRESS_RISK", "low"),
        "evi_last": ("HIGH_VEGETATION_STRESS_RISK", "low"),
        "rain_30d_mm": ("PERSISTENT_RAINFALL_DEFICIT", "low"),
        "rain_90d_mm": ("PERSISTENT_RAINFALL_DEFICIT", "low"),
        "rain_7d_mm": ("PERSISTENT_RAINFALL_DEFICIT", "low"),
        "dry_spell_days": ("PERSISTENT_RAINFALL_DEFICIT", "high"),
        "gwet_top_7d": ("SOIL_MOISTURE_DEFICIT", "low"),
        "gwet_top_30d": ("SOIL_MOISTURE_DEFICIT", "low"),
        "gwet_root_30d": ("SOIL_MOISTURE_DEFICIT", "low"),
        "t2m_30d_c": ("ELEVATED_TEMPERATURE_STRESS", "high"),
        "t2m_max_30d_c": ("ELEVATED_TEMPERATURE_STRESS", "high"),
        "t2m_7d_c": ("ELEVATED_TEMPERATURE_STRESS", "high"),
        "heavy_rain_days_30d": ("PERSISTENT_RAINFALL_DEFICIT", "low"),
        "vegetation_valid_pixel_fraction": ("LOW_VEGETATION_DATA_COVERAGE", "low"),
    },
    "flood": {
        "level_ratio_moderate": ("RIVER_LEVEL_NEAR_THRESHOLD", "high"),
        "current_level_m": ("RIVER_LEVEL_NEAR_THRESHOLD", "high"),
        "distance_to_moderate_m": ("RIVER_LEVEL_NEAR_THRESHOLD", "low"),
        "level_change_1d": ("RAPID_RIVER_RISE", "high"),
        "level_change_3d": ("RAPID_RIVER_RISE", "high"),
        "level_change_7d": ("RAPID_RIVER_RISE", "high"),
        "level_max_7d": ("RIVER_LEVEL_NEAR_THRESHOLD", "high"),
        "level_mean_7d": ("RIVER_LEVEL_NEAR_THRESHOLD", "high"),
        "rain_1d_mm": ("HEAVY_ANTECEDENT_RAINFALL", "high"),
        "rain_3d_mm": ("HEAVY_ANTECEDENT_RAINFALL", "high"),
        "rain_7d_mm": ("HEAVY_ANTECEDENT_RAINFALL", "high"),
        "rain_30d_mm": ("HEAVY_ANTECEDENT_RAINFALL", "high"),
        "heavy_rain_days_7d": ("HEAVY_ANTECEDENT_RAINFALL", "high"),
        "gwet_top_7d": ("SATURATED_ANTECEDENT_SOIL", "high"),
        "gwet_top_30d": ("SATURATED_ANTECEDENT_SOIL", "high"),
        "gwet_root_30d": ("SATURATED_ANTECEDENT_SOIL", "high"),
        "t2m_7d_c": ("ELEVATED_TEMPERATURE_STRESS", "high"),
    },
    "food_security": {
        "previous_ipc3plus_percentage": ("IPC_DETERIORATION_SIGNAL", "high"),
        "market_usdkg_90d_median": ("MARKET_PRICE_STRESS", "high"),
        "market_price_change_previous_90d": ("MARKET_PRICE_STRESS", "high"),
        "market_price_anomaly_365d": ("MARKET_PRICE_STRESS", "high"),
        "rain_30d_mm": ("PERSISTENT_RAINFALL_DEFICIT", "low"),
        "rain_90d_mm": ("PERSISTENT_RAINFALL_DEFICIT", "low"),
        "dry_days_30d": ("PERSISTENT_RAINFALL_DEFICIT", "high"),
        "t2m_30d_c": ("ELEVATED_TEMPERATURE_STRESS", "high"),
        "t2m_max_30d_c": ("ELEVATED_TEMPERATURE_STRESS", "high"),
        "gwet_top_30d": ("SOIL_MOISTURE_DEFICIT", "low"),
        "gwet_root_30d": ("SOIL_MOISTURE_DEFICIT", "low"),
        "ndvi_last": ("HIGH_VEGETATION_STRESS_RISK", "low"),
        "ndvi_change": ("HIGH_VEGETATION_STRESS_RISK", "low"),
        "log_region_population": ("POPULATION_CONTEXT", "high"),
    },
}


def local_drivers(bundle: ModelBundle, row: pd.Series, track: str, top_n: int = 5) -> list[dict[str, Any]]:
    """Median-perturbation local explanation for one operational observation."""
    frame = pd.DataFrame([row[bundle.feature_names]])
    base_probability = float(bundle.predict_probability(frame)[0])
    contributions = []
    for feature in bundle.feature_names:
        changed = frame.copy()
        changed.loc[:, feature] = bundle.training_medians[feature]
        changed_probability = float(bundle.predict_probability(changed)[0])
        delta = base_probability - changed_probability
        observed = row[feature]
        code_map = REASON_CODE_MAP.get(track, {})
        reason_code = None
        if feature in code_map and pd.notna(observed):
            code, direction = code_map[feature]
            median = bundle.training_medians[feature]
            supports_direction = (observed < median) if direction == "low" else (observed > median)
            if supports_direction and delta > 0:
                reason_code = code
        contributions.append(
            {
                "feature": feature,
                "observed_value": None if pd.isna(observed) else float(observed),
                "training_median": bundle.training_medians[feature],
                "probability_change_if_replaced_by_training_median": delta,
                "reason_code": reason_code,
            }
        )
    contributions.sort(key=lambda item: abs(item["probability_change_if_replaced_by_training_median"]), reverse=True)
    return contributions[:top_n]


def reason_codes(local_driver_rows: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for row in local_driver_rows:
        code = row.get("reason_code")
        if code and code not in seen and row["probability_change_if_replaced_by_training_median"] > 0:
            seen.append(code)
    return seen
