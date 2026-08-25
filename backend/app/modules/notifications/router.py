from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AlertStatus, DeliveryStatus
from app.db.models.core import ActionItem, ActionPlan, Alert, NotificationDelivery, RiskSignal
from app.db.session import get_db
from app.modules.auth.dependencies import (
    Principal,
    get_current_principal,
    has_access,
    require_access,
)
from app.modules.notifications.schemas import DeliveryCreate, DeliveryListResponse, DeliveryResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _context(
    db: Session, alert_id: UUID | None, action_item_id: UUID | None
) -> tuple[Alert, RiskSignal]:
    if alert_id:
        alert = db.get(Alert, alert_id)
    else:
        item = db.get(ActionItem, action_item_id)
        plan = db.get(ActionPlan, item.plan_id) if item else None
        alert = db.get(Alert, plan.alert_id) if plan else None
    signal = db.get(RiskSignal, alert.signal_id) if alert else None
    if alert is None or signal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification event entity not found")
    return alert, signal


@router.get("/deliveries", response_model=list[DeliveryListResponse])
def list_deliveries(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[DeliveryListResponse]:
    visible: list[DeliveryListResponse] = []
    deliveries = db.scalars(
        select(NotificationDelivery).order_by(NotificationDelivery.created_at.desc())
    ).all()
    for delivery in deliveries:
        alert, signal = _context(db, delivery.alert_id, delivery.action_item_id)
        is_recipient = delivery.recipient_key == str(principal.user_id)
        if not is_recipient and not has_access(
            principal, "notifications.read", alert.classification, signal.admin_unit_id
        ):
            continue
        visible.append(
            DeliveryListResponse(
                id=delivery.id,
                event_key=delivery.event_key,
                event_title=alert.title,
                channel=delivery.channel,
                status=delivery.status,
                recipient_is_current_user=is_recipient,
                attempt_count=delivery.attempt_count,
                next_attempt_at=delivery.next_attempt_at,
                acknowledged_at=delivery.acknowledged_at,
                escalated_at=delivery.escalated_at,
                escalation_level=delivery.escalation_level,
                last_error_code=delivery.last_error_code,
                last_attempted_at=delivery.last_attempted_at,
                dead_lettered_at=delivery.dead_lettered_at,
            )
        )
    return visible


@router.post("/deliveries", response_model=DeliveryResponse, status_code=status.HTTP_201_CREATED)
def create_delivery(
    body: DeliveryCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> NotificationDelivery:
    alert, signal = _context(db, body.alert_id, body.action_item_id)
    require_access(principal, "notifications.send", alert.classification, signal.admin_unit_id)
    if body.alert_id and alert.status is not AlertStatus.PUBLISHED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Warning notifications require publication")
    existing = db.scalar(
        select(NotificationDelivery).where(
            NotificationDelivery.event_key == body.event_key,
            NotificationDelivery.recipient_key == body.recipient_key,
            NotificationDelivery.channel == body.channel,
        )
    )
    if existing:
        return existing
    delivery = NotificationDelivery(
        **body.model_dump(), status=DeliveryStatus.QUEUED, attempt_count=0, escalation_level=0
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    return delivery


@router.post("/deliveries/{delivery_id}/acknowledgement", response_model=DeliveryResponse)
def acknowledge(
    delivery_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> NotificationDelivery:
    delivery = db.get(NotificationDelivery, delivery_id)
    if delivery is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery not found")
    alert, signal = _context(db, delivery.alert_id, delivery.action_item_id)
    is_recipient = delivery.recipient_key == str(principal.user_id)
    if not is_recipient:
        require_access(
            principal, "notifications.manage", alert.classification, signal.admin_unit_id
        )
    delivery.status = DeliveryStatus.ACKNOWLEDGED
    delivery.acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(delivery)
    return delivery


@router.post("/deliveries/{delivery_id}/escalation", response_model=DeliveryResponse)
def escalate(
    delivery_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> NotificationDelivery:
    delivery = db.get(NotificationDelivery, delivery_id)
    if delivery is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery not found")
    alert, signal = _context(db, delivery.alert_id, delivery.action_item_id)
    require_access(principal, "notifications.escalate", alert.classification, signal.admin_unit_id)
    if delivery.acknowledged_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "Acknowledged delivery cannot be escalated")
    delivery.escalation_level += 1
    delivery.escalated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(delivery)
    return delivery
