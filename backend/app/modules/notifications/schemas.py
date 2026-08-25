from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums import DeliveryStatus


class DeliveryCreate(BaseModel):
    event_key: str = Field(min_length=3, max_length=255)
    recipient_key: str = Field(min_length=1, max_length=255)
    channel: str = Field(pattern="^(in_app|email|sms|push|webhook)$")
    alert_id: UUID | None = None
    action_item_id: UUID | None = None

    @model_validator(mode="after")
    def one_event_entity(self) -> "DeliveryCreate":
        if (self.alert_id is None) == (self.action_item_id is None):
            raise ValueError("Exactly one of alert_id or action_item_id is required")
        return self


class DeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    event_key: str
    recipient_key: str
    channel: str
    alert_id: UUID | None
    action_item_id: UUID | None
    status: DeliveryStatus
    attempt_count: int
    next_attempt_at: datetime | None
    acknowledged_at: datetime | None
    escalated_at: datetime | None
    escalation_level: int
    provider_message_id: str | None
    last_error_code: str | None
    last_attempted_at: datetime | None
    dead_lettered_at: datetime | None


class DeliveryListResponse(BaseModel):
    id: UUID
    event_key: str
    event_title: str
    channel: str
    status: DeliveryStatus
    recipient_is_current_user: bool
    attempt_count: int
    next_attempt_at: datetime | None
    acknowledged_at: datetime | None
    escalated_at: datetime | None
    escalation_level: int
    last_error_code: str | None
    last_attempted_at: datetime | None
    dead_lettered_at: datetime | None
