from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import or_, select

from app.core.config import get_settings
from app.core.enums import DeliveryStatus
from app.db.models.core import NotificationDelivery
from app.db.session import SessionLocal
from app.integrations.notifications.providers import notification_provider
from app.modules.notifications.service import dispatch_delivery
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.notifications.dispatch_notification")
def dispatch_notification(delivery_id: str) -> str:
    with SessionLocal() as db:
        delivery = dispatch_delivery(
            db,
            UUID(delivery_id),
            notification_provider(get_settings()),
        )
        return delivery.status.value


@celery_app.task(name="app.workers.tasks.notifications.dispatch_due_notifications")
def dispatch_due_notifications(limit: int = 100) -> dict[str, int]:
    bounded_limit = min(max(limit, 1), 500)
    now = datetime.now(timezone.utc)
    dispatched = 0
    with SessionLocal() as db:
        delivery_ids = list(
            db.scalars(
                select(NotificationDelivery.id)
                .where(
                    NotificationDelivery.status.in_(
                        [DeliveryStatus.QUEUED, DeliveryStatus.FAILED]
                    ),
                    or_(
                        NotificationDelivery.next_attempt_at.is_(None),
                        NotificationDelivery.next_attempt_at <= now,
                    ),
                    NotificationDelivery.dead_lettered_at.is_(None),
                )
                .order_by(NotificationDelivery.created_at)
                .limit(bounded_limit)
            ).all()
        )
        provider = notification_provider(get_settings())
        for delivery_id in delivery_ids:
            dispatch_delivery(db, delivery_id, provider, now=now)
            dispatched += 1
    return {"selected": len(delivery_ids), "dispatched": dispatched}
