from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class NotificationMessage:
    event_key: str
    recipient_key: str
    channel: str
    title: str
    body: str
    classification: str


@dataclass(frozen=True)
class SendResult:
    accepted: bool
    delivered: bool = False
    provider_message_id: str | None = None
    retryable: bool = False
    error_code: str | None = None


class NotificationProvider(Protocol):
    def send(self, message: NotificationMessage) -> SendResult: ...
