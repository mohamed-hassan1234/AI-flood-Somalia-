from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.enums import DeliveryStatus
from app.db.models.core import ActionItem, ActionPlan, Alert, NotificationDelivery
from app.integrations.notifications.port import (
    NotificationMessage,
    NotificationProvider,
    SendResult,
)


@dataclass(frozen=True)
class RetryDecision:
    attempt: int
    retry_at: datetime | None
    dead_letter: bool


def retry_decision(
    attempt: int, max_attempts: int = 5, now: datetime | None = None
) -> RetryDecision:
    next_attempt = attempt + 1
    if next_attempt >= max_attempts:
        return RetryDecision(next_attempt, None, True)
    delay = min(2**attempt, 60)
    current = now or datetime.now(timezone.utc)
    return RetryDecision(next_attempt, current + timedelta(minutes=delay), False)


def deduplication_key(event_key: str, recipient_key: str, channel: str) -> str:
    return f"{event_key}:{recipient_key}:{channel}"


def _message(db: Session, delivery: NotificationDelivery) -> NotificationMessage:
    if delivery.alert_id:
        alert = db.get(Alert, delivery.alert_id)
        body = alert.summary if alert else None
    else:
        item = db.get(ActionItem, delivery.action_item_id)
        plan = db.get(ActionPlan, item.plan_id) if item else None
        alert = db.get(Alert, plan.alert_id) if plan else None
        body = item.description if item else None
    if alert is None or body is None:
        raise ValueError("Notification event entity is unavailable")
    return NotificationMessage(
        event_key=delivery.event_key,
        recipient_key=delivery.recipient_key,
        channel=delivery.channel,
        title=alert.title,
        body=body,
        classification=alert.classification.value,
    )


def dispatch_delivery(
    db: Session,
    delivery_id: UUID,
    provider: NotificationProvider,
    *,
    now: datetime | None = None,
    max_attempts: int = 5,
) -> NotificationDelivery:
    delivery = db.get(NotificationDelivery, delivery_id)
    if delivery is None:
        raise ValueError("Notification delivery is unavailable")
    if delivery.status not in {DeliveryStatus.QUEUED, DeliveryStatus.FAILED}:
        return delivery
    current = now or datetime.now(timezone.utc)
    if delivery.next_attempt_at and _aware(delivery.next_attempt_at) > _aware(current):
        return delivery
    try:
        result = provider.send(_message(db, delivery))
    except Exception:  # noqa: BLE001 - provider boundary must not crash the worker loop
        result = SendResult(False, retryable=True, error_code="provider_exception")
    delivery.last_attempted_at = current
    delivery.attempt_count += 1
    if result.accepted:
        delivery.status = DeliveryStatus.DELIVERED if result.delivered else DeliveryStatus.SENT
        delivery.provider_message_id = result.provider_message_id
        delivery.last_error_code = None
        delivery.next_attempt_at = None
        delivery.dead_lettered_at = None
    else:
        delivery.status = DeliveryStatus.FAILED
        delivery.last_error_code = (result.error_code or "provider_rejected")[:80]
        decision = retry_decision(delivery.attempt_count - 1, max_attempts=max_attempts, now=current)
        if result.retryable and not decision.dead_letter:
            delivery.next_attempt_at = decision.retry_at
        else:
            delivery.next_attempt_at = None
            delivery.dead_lettered_at = current
    db.commit()
    db.refresh(delivery)
    return delivery


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
