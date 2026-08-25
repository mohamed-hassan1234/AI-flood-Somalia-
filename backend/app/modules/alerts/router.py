from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AlertStatus
from app.db.models.core import Alert, AuditEvent, RiskSignal
from app.db.session import get_db
from app.modules.alerts.schemas import (
    AlertCreate,
    AlertListResponse,
    AlertResponse,
    AlertTransition,
)
from app.modules.alerts.service import (
    REQUIRED_CAPABILITY,
    InvalidTransition,
    TransitionRequest,
    transition,
)
from app.modules.auth.dependencies import (
    Principal,
    get_current_principal,
    grants_for,
    has_access,
    require_access,
)

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _load(db: Session, alert_id: UUID) -> tuple[Alert, RiskSignal]:
    alert = db.get(Alert, alert_id)
    signal = db.get(RiskSignal, alert.signal_id) if alert else None
    if alert is None or signal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    return alert, signal


def _audit(db: Session, principal: Principal, action: str, alert: Alert) -> None:
    db.add(
        AuditEvent(
            id=uuid4(),
            occurred_at=datetime.now(timezone.utc),
            actor_id=principal.user_id,
            action=action,
            entity_type="alert",
            entity_id=alert.id,
            details={"status": alert.status.value},
        )
    )


@router.post("", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
def create_alert(
    body: AlertCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Alert:
    signal = db.get(RiskSignal, body.signal_id)
    if signal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Risk signal not found")
    require_access(principal, "alerts.create", body.classification, signal.admin_unit_id)
    alert = Alert(
        signal_id=signal.id,
        status=AlertStatus.DRAFT,
        classification=body.classification,
        title=body.title,
        summary=body.summary,
    )
    db.add(alert)
    db.flush()
    _audit(db, principal, "alerts.create", alert)
    db.commit()
    db.refresh(alert)
    return alert


@router.get("", response_model=list[AlertListResponse])
def list_alerts(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[AlertListResponse]:
    grants_for(principal, "alerts.read")
    rows = db.execute(
        select(Alert, RiskSignal).join(RiskSignal, RiskSignal.id == Alert.signal_id)
        .order_by(Alert.created_at.desc())
    ).all()
    return [
        AlertListResponse(
            id=alert.id,
            signal_id=alert.signal_id,
            status=alert.status,
            classification=alert.classification,
            title=alert.title,
            summary=alert.summary,
            admin_unit_id=signal.admin_unit_id,
            risk_domain=signal.domain,
            risk_level=signal.level,
            target_period=signal.target_period,
            created_at=alert.created_at,
            published_at=alert.published_at,
        )
        for alert, signal in rows
        if has_access(
            principal,
            "alerts.read",
            alert.classification,
            signal.admin_unit_id,
        )
    ]


@router.get("/partner-warnings", response_model=list[AlertListResponse])
def list_partner_warnings(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[AlertListResponse]:
    grants_for(principal, "alerts.read")
    rows = db.execute(
        select(Alert, RiskSignal)
        .join(RiskSignal, RiskSignal.id == Alert.signal_id)
        .where(Alert.status == AlertStatus.PUBLISHED)
        .order_by(Alert.published_at.desc())
    ).all()
    return [
        AlertListResponse(
            id=alert.id,
            signal_id=alert.signal_id,
            status=alert.status,
            classification=alert.classification,
            title=alert.title,
            summary=alert.summary,
            admin_unit_id=signal.admin_unit_id,
            risk_domain=signal.domain,
            risk_level=signal.level,
            target_period=signal.target_period,
            created_at=alert.created_at,
            published_at=alert.published_at,
        )
        for alert, signal in rows
        if has_access(
            principal,
            "alerts.read",
            alert.classification,
            signal.admin_unit_id,
        )
    ]


@router.post("/{alert_id}/transitions", response_model=AlertResponse)
def transition_alert(
    alert_id: UUID,
    body: AlertTransition,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Alert:
    alert, signal = _load(db, alert_id)
    capability = REQUIRED_CAPABILITY.get(body.target)
    if capability is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported transition target")
    require_access(principal, capability, alert.classification, signal.admin_unit_id)
    try:
        alert.status = transition(
            TransitionRequest(alert.status, body.target, capability), {capability}
        )
    except (InvalidTransition, PermissionError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    if alert.status is AlertStatus.APPROVED:
        alert.approved_by = principal.user_id
    if alert.status is AlertStatus.PUBLISHED:
        alert.published_at = datetime.now(timezone.utc)
    _audit(db, principal, capability, alert)
    db.commit()
    db.refresh(alert)
    return alert


@router.get("/{alert_id}", response_model=AlertResponse)
def get_alert(
    alert_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Alert:
    alert, signal = _load(db, alert_id)
    require_access(principal, "alerts.read", alert.classification, signal.admin_unit_id)
    return alert
