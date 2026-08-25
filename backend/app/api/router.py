from fastapi import APIRouter

from app.core.enums import AlertStatus, Classification, RiskDomain, RiskLevel
from app.modules.administration.router import router as administration_router
from app.modules.alerts.router import router as alerts_router
from app.modules.auth.router import router as auth_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.data_sources.router import router as data_sources_router
from app.modules.early_actions.router import router as early_actions_router
from app.modules.exposure.router import router as exposure_router
from app.modules.field_verification.router import router as field_verification_router
from app.modules.geography.router import router as geography_router
from app.modules.indicators.router import router as indicators_router
from app.modules.ml_registry.router import router as ml_registry_router
from app.modules.notifications.router import router as notifications_router
from app.modules.observations.router import router as observations_router
from app.modules.outcomes.router import router as outcomes_router
from app.modules.public_portal.router import router as public_router
from app.modules.reports.router import router as reports_router
from app.modules.risks.router import router as risks_router
from app.modules.scenarios.router import router as scenarios_router
from app.modules.seasons.router import router as seasons_router

router = APIRouter()
router.include_router(administration_router)
router.include_router(alerts_router)
router.include_router(auth_router)
router.include_router(geography_router)
router.include_router(indicators_router)
router.include_router(observations_router)
router.include_router(notifications_router)
router.include_router(ml_registry_router)
router.include_router(risks_router)
router.include_router(outcomes_router)
router.include_router(scenarios_router)
router.include_router(seasons_router)
router.include_router(public_router)
router.include_router(reports_router)
router.include_router(data_sources_router)
router.include_router(dashboard_router)
router.include_router(field_verification_router)
router.include_router(exposure_router)
router.include_router(early_actions_router)


@router.get("/meta", tags=["platform"])
def platform_metadata() -> dict[str, object]:
    return {
        "risk_domains": [item.value for item in RiskDomain],
        "risk_levels": [item.value for item in RiskLevel],
        "alert_statuses": [item.value for item in AlertStatus],
        "classifications": [item.value for item in Classification],
        "official_ipc_output": False,
        "automatic_warning_publication": False,
    }
