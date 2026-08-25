from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AlertStatus, Classification, ReportStatus
from app.db.models.core import AdminUnit, Alert, Report, RiskSignal
from app.db.session import get_db
from app.modules.public_portal.schemas import PublicReportResponse, PublicWarningResponse

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/reports", response_model=list[PublicReportResponse])
def list_public_reports(
    db: Annotated[Session, Depends(get_db)],
) -> list[PublicReportResponse]:
    rows = db.execute(
        select(Report, AdminUnit)
        .join(AdminUnit, AdminUnit.id == Report.admin_unit_id)
        .where(
            Report.status == ReportStatus.PUBLISHED,
            Report.classification == Classification.PUBLIC,
            Report.published_at.is_not(None),
        )
        .order_by(Report.published_at.desc())
    ).all()
    return [
        PublicReportResponse(
            id=report.id,
            title=report.title,
            reporting_period=report.reporting_period,
            admin_unit_id=unit.id,
            admin_unit_name=unit.name,
            boundary_version=report.boundary_version,
            sections=report.sections,
            findings=report.findings,
            recommendations=report.recommendations,
            published_at=report.published_at,
        )
        for report, unit in rows
        if report.published_at is not None
    ]


def _projection(alert: Alert, signal: RiskSignal, unit: AdminUnit) -> PublicWarningResponse:
    if alert.published_at is None:
        raise ValueError("Published warning has no publication timestamp")
    return PublicWarningResponse(
        id=alert.id,
        title=alert.title,
        summary=alert.summary,
        risk_domain=signal.domain,
        risk_level=signal.level,
        target_period=signal.target_period,
        admin_unit_id=unit.id,
        admin_unit_name=unit.name,
        boundary_version=unit.boundary_version,
        published_at=alert.published_at,
    )


@router.get("/warnings", response_model=list[PublicWarningResponse])
def list_public_warnings(
    db: Annotated[Session, Depends(get_db)],
) -> list[PublicWarningResponse]:
    rows = db.execute(
        select(Alert, RiskSignal, AdminUnit)
        .join(RiskSignal, RiskSignal.id == Alert.signal_id)
        .join(AdminUnit, AdminUnit.id == RiskSignal.admin_unit_id)
        .where(
            Alert.status == AlertStatus.PUBLISHED,
            Alert.classification == Classification.PUBLIC,
            Alert.published_at.is_not(None),
        )
        .order_by(Alert.published_at.desc())
    ).all()
    return [_projection(alert, signal, unit) for alert, signal, unit in rows]


@router.get("/warnings/{warning_id}", response_model=PublicWarningResponse)
def get_public_warning(
    warning_id: UUID, db: Annotated[Session, Depends(get_db)]
) -> PublicWarningResponse:
    row = db.execute(
        select(Alert, RiskSignal, AdminUnit)
        .join(RiskSignal, RiskSignal.id == Alert.signal_id)
        .join(AdminUnit, AdminUnit.id == RiskSignal.admin_unit_id)
        .where(
            Alert.id == warning_id,
            Alert.status == AlertStatus.PUBLISHED,
            Alert.classification == Classification.PUBLIC,
            Alert.published_at.is_not(None),
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Public warning not found")
    return _projection(*row)
