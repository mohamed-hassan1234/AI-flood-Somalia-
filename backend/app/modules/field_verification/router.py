from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AlertStatus, VerificationStatus
from app.db.models.core import (
    Alert,
    AuditEvent,
    FieldReport,
    RiskSignal,
    User,
    VerificationTask,
)
from app.db.session import get_db
from app.modules.auth.dependencies import (
    Principal,
    get_current_principal,
    grants_for,
    has_access,
    require_access,
)
from app.modules.field_verification.schemas import (
    FieldReportResponse,
    FieldReportSubmit,
    VerificationReview,
    VerificationTaskCreate,
    VerificationTaskListResponse,
    VerificationTaskResponse,
)
from app.modules.field_verification.service import transition

router = APIRouter(prefix="/field-verification", tags=["field verification"])


def _context(db: Session, task_id: UUID) -> tuple[VerificationTask, Alert, RiskSignal]:
    task = db.get(VerificationTask, task_id)
    alert = db.get(Alert, task.alert_id) if task else None
    signal = db.get(RiskSignal, alert.signal_id) if alert else None
    if task is None or alert is None or signal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Verification task not found")
    return task, alert, signal


def _audit(
    db: Session, principal: Principal, action: str, entity_id: UUID, details: dict[str, object]
) -> None:
    db.add(
        AuditEvent(
            id=uuid4(),
            occurred_at=datetime.now(timezone.utc),
            actor_id=principal.user_id,
            action=action,
            entity_type="verification_task",
            entity_id=entity_id,
            details=details,
        )
    )


@router.post("/tasks", response_model=VerificationTaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    body: VerificationTaskCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> VerificationTask:
    alert = db.get(Alert, body.alert_id)
    signal = db.get(RiskSignal, alert.signal_id) if alert else None
    if alert is None or signal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    require_access(principal, "field_tasks.create", alert.classification, signal.admin_unit_id)
    if alert.status not in {AlertStatus.IN_REVIEW, AlertStatus.VERIFICATION_REQUIRED}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Alert is not awaiting verification")
    if body.assigned_to is not None and db.get(User, body.assigned_to) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Assigned user does not exist")
    task = VerificationTask(
        alert_id=alert.id,
        admin_unit_id=signal.admin_unit_id,
        assigned_to=body.assigned_to,
        due_at=body.due_at,
        priority=body.priority,
        status=VerificationStatus.OPEN,
        form_schema=body.form_schema,
    )
    db.add(task)
    db.flush()
    alert.status = AlertStatus.VERIFICATION_REQUIRED
    _audit(db, principal, "field_tasks.create", task.id, {"alert_id": str(alert.id)})
    db.commit()
    db.refresh(task)
    return task


@router.get("/tasks", response_model=list[VerificationTaskListResponse])
def list_tasks(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[VerificationTaskListResponse]:
    grants_for(principal, "field_tasks.read")
    rows = db.execute(
        select(VerificationTask, Alert, RiskSignal)
        .join(Alert, Alert.id == VerificationTask.alert_id)
        .join(RiskSignal, RiskSignal.id == Alert.signal_id)
        .order_by(VerificationTask.due_at)
    ).all()
    reviewer = "field_reports.verify" in principal.capabilities
    return [
        VerificationTaskListResponse(
            id=task.id,
            alert_id=alert.id,
            alert_title=alert.title,
            classification=alert.classification,
            admin_unit_id=task.admin_unit_id,
            risk_domain=signal.domain,
            assigned_to=task.assigned_to,
            due_at=task.due_at,
            priority=task.priority,
            status=task.status,
        )
        for task, alert, signal in rows
        if has_access(
            principal,
            "field_tasks.read",
            alert.classification,
            signal.admin_unit_id,
        )
        and (reviewer or task.assigned_to in {None, principal.user_id})
    ]


@router.post(
    "/tasks/{task_id}/reports",
    response_model=FieldReportResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_report(
    task_id: UUID,
    body: FieldReportSubmit,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> FieldReport:
    task, alert, signal = _context(db, task_id)
    require_access(principal, "field_reports.submit", alert.classification, signal.admin_unit_id)
    if task.assigned_to is not None and task.assigned_to != principal.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Task is assigned to another reporter")
    if db.scalar(select(FieldReport.id).where(FieldReport.task_id == task.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A report already exists for this task")
    try:
        task.status = transition(
            task.status, VerificationStatus.SUBMITTED, {"field_reports.submit"}
        )
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    report = FieldReport(
        task_id=task.id,
        reporter_id=principal.user_id,
        answers=body.answers,
        evidence_objects=body.evidence_objects,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(report)
    db.flush()
    _audit(db, principal, "field_reports.submit", task.id, {"report_id": str(report.id)})
    db.commit()
    db.refresh(report)
    return report


@router.post("/tasks/{task_id}/reviews", response_model=VerificationTaskResponse)
def review_report(
    task_id: UUID,
    body: VerificationReview,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> VerificationTask:
    task, alert, signal = _context(db, task_id)
    require_access(principal, "field_reports.verify", alert.classification, signal.admin_unit_id)
    if body.target not in {
        VerificationStatus.VERIFIED,
        VerificationStatus.REJECTED,
        VerificationStatus.MORE_EVIDENCE,
    }:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported review outcome")
    report = db.scalar(select(FieldReport).where(FieldReport.task_id == task.id))
    if report is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No submitted report exists")
    try:
        task.status = transition(task.status, body.target, {"field_reports.verify"})
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    report.review_notes = body.notes
    if task.status is VerificationStatus.VERIFIED:
        alert.status = AlertStatus.VERIFIED
    _audit(db, principal, f"field_reports.{body.target.value}", task.id, {"notes_recorded": True})
    db.commit()
    db.refresh(task)
    return task
