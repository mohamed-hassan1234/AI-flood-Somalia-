import hashlib
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import Settings
from app.integrations.notifications.port import (
    NotificationMessage,
    NotificationProvider,
    SendResult,
)


class DevelopmentSinkProvider:
    """Accepts without external transmission and never logs message or recipient content."""

    def send(self, message: NotificationMessage) -> SendResult:
        fingerprint = hashlib.sha256(
            f"{message.event_key}:{message.recipient_key}:{message.channel}".encode()
        ).hexdigest()[:24]
        return SendResult(accepted=True, provider_message_id=f"development-{fingerprint}")


class RoutingNotificationProvider:
    def __init__(self, external: NotificationProvider) -> None:
        self.external = external

    def send(self, message: NotificationMessage) -> SendResult:
        if message.channel == "in_app":
            return SendResult(
                accepted=True,
                delivered=True,
                provider_message_id=f"in-app-{message.event_key[:64]}",
            )
        return self.external.send(message)


class GatewayNotificationProvider:
    def __init__(self, base_url: str, token: str, timeout_seconds: float) -> None:
        self.endpoint = f"{base_url.rstrip('/')}/send"
        self.token = token
        self.timeout_seconds = timeout_seconds

    def send(self, message: NotificationMessage) -> SendResult:
        request = Request(
            self.endpoint,
            data=json.dumps(
                {
                    "event_key": message.event_key,
                    "recipient_key": message.recipient_key,
                    "channel": message.channel,
                    "title": message.title,
                    "body": message.body,
                    "classification": message.classification,
                }
            ).encode(),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read(64 * 1024))
        except HTTPError as exc:
            retryable = exc.code == 429 or exc.code >= 500
            return SendResult(False, retryable=retryable, error_code=f"gateway_http_{exc.code}")
        except (URLError, TimeoutError):
            return SendResult(False, retryable=True, error_code="gateway_unavailable")
        except (json.JSONDecodeError, ValueError):
            return SendResult(False, retryable=False, error_code="gateway_invalid_response")
        accepted = payload.get("accepted") is True
        return SendResult(
            accepted=accepted,
            delivered=payload.get("delivered") is True,
            provider_message_id=(
                str(payload["message_id"])[:255] if payload.get("message_id") else None
            ),
            retryable=payload.get("retryable") is True,
            error_code=None if accepted else str(payload.get("error_code", "gateway_rejected"))[:80],
        )


def notification_provider(settings: Settings) -> NotificationProvider:
    if settings.notification_provider == "development":
        return RoutingNotificationProvider(DevelopmentSinkProvider())
    if settings.notification_gateway_url is None or settings.notification_gateway_token is None:
        raise RuntimeError("Notification gateway configuration is incomplete")
    return RoutingNotificationProvider(
        GatewayNotificationProvider(
            settings.notification_gateway_url,
            settings.notification_gateway_token.get_secret_value(),
            settings.notification_timeout_seconds,
        )
    )
