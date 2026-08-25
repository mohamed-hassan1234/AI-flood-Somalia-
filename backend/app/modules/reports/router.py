from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AlertStatus, ReportStatus
from app.db.models.core import AdminUnit, Alert, AuditEvent, Report, RiskSignal
from app.db.session import get_db
from app.modules.auth.dependencies import (
    Principal,
    get_current_principal,
    has_access,
    require_access,
)
from app.modules.reports.schemas import ReportCreate, ReportResponse
from app.modules.reports.service import preserves_classification, report_csv, report_html

router = APIRouter(prefix="/reports", tags=["reports"])


def _load(db: Session, report_id: UUID) -> Report:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    return report


def _audit(db: Session, principal: Principal, action: str, report: Report) -> None:
    db.add(
        AuditEvent(
            id=uuid4(),
            occurred_at=datetime.now(timezone.utc),
            actor_id=principal.user_id,
            action=action,
            entity_type="report",
            entity_id=report.id,
            details={"status": report.status.value, "classification": report.classification.value},
        )
    )


@router.post("", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def create_report(
    body: ReportCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Report:
    row = db.execute(
        select(Alert, RiskSignal, AdminUnit)
        .join(RiskSignal, RiskSignal.id == Alert.signal_id)
        .join(AdminUnit, AdminUnit.id == RiskSignal.admin_unit_id)
        .where(Alert.id == body.alert_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    alert, signal, unit = row
    require_access(principal, "reports.generate", body.classification, signal.admin_unit_id)
    if alert.status is not AlertStatus.PUBLISHED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Reports require a published source alert")
    if not preserves_classification(alert.classification, body.classification):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Report cannot reduce source classification")
    report = Report(
        alert_id=alert.id,
        admin_unit_id=signal.admin_unit_id,
        created_by=principal.user_id,
        classification=body.classification,
        status=ReportStatus.DRAFT,
        title=body.title,
        reporting_period=body.reporting_period,
        boundary_version=unit.boundary_version,
        sections=[section.model_dump() for section in body.sections],
        findings=body.findings,
        recommendations=body.recommendations,
        source_lineage=[reference.model_dump(mode="json") for reference in body.source_lineage],
    )
    db.add(report)
    db.flush()
    _audit(db, principal, "reports.generate", report)
    db.commit()
    db.refresh(report)
    return report


@router.post("/{report_id}/publish", response_model=ReportResponse)
def publish_report(
    report_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Report:
    report = _load(db, report_id)
    require_access(principal, "reports.publish", report.classification, report.admin_unit_id)
    if report.status is not ReportStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only draft reports can be published")
    report.status = ReportStatus.PUBLISHED
    report.published_by = principal.user_id
    report.published_at = datetime.now(timezone.utc)
    _audit(db, principal, "reports.publish", report)
    db.commit()
    db.refresh(report)
    return report


@router.get("", response_model=list[ReportResponse])
def list_reports(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Report]:
    reports = db.scalars(
        select(Report).where(Report.status == ReportStatus.PUBLISHED).order_by(Report.published_at.desc())
    ).all()
    return [
        report
        for report in reports
        if has_access(principal, "reports.read", report.classification, report.admin_unit_id)
    ]


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(
    report_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Report:
    report = _load(db, report_id)
    require_access(principal, "reports.read", report.classification, report.admin_unit_id)
    if report.status is not ReportStatus.PUBLISHED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Published report not found")
    return report


@router.get("/{report_id}/export")
def export_report(
    report_id: UUID,
    format: Literal["csv", "html"],
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    report = get_report(report_id, principal, db)
    if format == "csv":
        return Response(
            report_csv(report),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="report-{report.id}.csv"'},
        )
    return Response(
        report_html(report),
        media_type="text/html",
        headers={
            "Content-Disposition": f'attachment; filename="report-{report.id}.html"',
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )
