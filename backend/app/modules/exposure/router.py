from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AlertStatus
from app.db.models.core import Alert, ExposureAssessment, RiskSignal
from app.db.session import get_db
from app.modules.auth.dependencies import (
    Principal,
    get_current_principal,
    has_access,
    require_access,
)
from app.modules.exposure.schemas import ExposureCreate, ExposureListResponse, ExposureResponse

router = APIRouter(prefix="/exposure", tags=["exposure"])


@router.get("/assessments", response_model=list[ExposureListResponse])
def list_assessments(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ExposureListResponse]:
    rows = db.execute(
        select(ExposureAssessment, Alert, RiskSignal)
        .join(Alert, Alert.id == ExposureAssessment.alert_id)
        .join(RiskSignal, RiskSignal.id == Alert.signal_id)
        .order_by(ExposureAssessment.created_at.desc())
    ).all()
    return [
        ExposureListResponse(
            id=assessment.id,
            alert_id=alert.id,
            alert_title=alert.title,
            classification=alert.classification.value,
            risk_domain=signal.domain.value,
            risk_level=signal.level.value,
            admin_unit_id=assessment.admin_unit_id,
            population=assessment.population,
            settlements=assessment.settlements,
            cropland_hectares=assessment.cropland_hectares,
            infrastructure=assessment.infrastructure,
            confidence=assessment.confidence,
            lineage_available=bool(assessment.source_lineage),
        )
        for assessment, alert, signal in rows
        if has_access(
            principal, "exposure.read", alert.classification, assessment.admin_unit_id
        )
    ]


@router.post("/assessments", response_model=ExposureResponse, status_code=status.HTTP_201_CREATED)
def create_assessment(
    body: ExposureCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> ExposureAssessment:
    alert = db.get(Alert, body.alert_id)
    signal = db.get(RiskSignal, alert.signal_id) if alert else None
    if alert is None or signal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    require_access(principal, "exposure.calculate", alert.classification, signal.admin_unit_id)
    if alert.status is not AlertStatus.PUBLISHED:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Exposure assessment requires a published warning"
        )
    existing = db.scalar(
        select(ExposureAssessment.id).where(ExposureAssessment.alert_id == alert.id)
    )
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "An exposure assessment already exists")
    assessment = ExposureAssessment(admin_unit_id=signal.admin_unit_id, **body.model_dump())
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return assessment


@router.get("/assessments/{assessment_id}", response_model=ExposureResponse)
def get_assessment(
    assessment_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> ExposureAssessment:
    assessment = db.get(ExposureAssessment, assessment_id)
    alert = db.get(Alert, assessment.alert_id) if assessment else None
    signal = db.get(RiskSignal, alert.signal_id) if alert else None
    if assessment is None or alert is None or signal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exposure assessment not found")
    require_access(principal, "exposure.read", alert.classification, signal.admin_unit_id)
    return assessment
