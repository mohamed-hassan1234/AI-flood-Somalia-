from app.core.enums import RiskDomain

DOMAIN_FEATURES: dict[RiskDomain, dict[str, float]] = {
    RiskDomain.DROUGHT: {
        "drought.rainfall_deficit": 0.40,
        "drought.vegetation_stress": 0.35,
        "drought.dry_spell": 0.25,
    },
    RiskDomain.RIVER_FLOOD: {
        "river.level_threshold_ratio": 0.50,
        "river.rate_of_rise": 0.30,
        "river.rainfall_forecast": 0.20,
    },
    RiskDomain.FLASH_FLOOD: {
        "flash.rainfall_intensity": 0.50,
        "flash.susceptibility": 0.30,
        "flash.rainfall_forecast": 0.20,
    },
    RiskDomain.FOOD_SECURITY: {
        "food.price_stress": 0.30,
        "food.nutrition_stress": 0.25,
        "food.displacement_stress": 0.20,
        "food.agriculture_stress": 0.25,
    },
}
