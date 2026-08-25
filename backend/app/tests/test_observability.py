import asyncio
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.core.middleware import RateLimitMiddleware, safe_request_id
from app.core.observability import FixedWindowRateLimiter, RedisFixedWindowRateLimiter
from app.db.session import get_db
from app.main import create_app


class FailingDatabase:
    def execute(self, _statement: object) -> None:
        raise SQLAlchemyError("synthetic database outage")


def test_fixed_window_rate_limit_resets_deterministically() -> None:
    now = [100.0]
    limiter = FixedWindowRateLimiter(2, 60, clock=lambda: now[0])
    assert limiter.check("client").remaining == 1
    assert limiter.check("client").remaining == 0
    denied = limiter.check("client")
    assert denied.allowed is False
    assert denied.retry_after_seconds == 60
    now[0] = 161.0
    assert limiter.check("client").allowed is True


def test_public_route_rate_limit_returns_retry_contract() -> None:
    limited = FastAPI()
    limited.add_middleware(
        RateLimitMiddleware,
        auth_limiter=FixedWindowRateLimiter(1, 60),
        public_limiter=FixedWindowRateLimiter(1, 60),
    )

    @limited.get("/api/v1/public/ping")
    def public_ping() -> dict[str, str]:
        return {"status": "ok"}

    client = TestClient(limited)
    first = client.get("/api/v1/public/ping")
    second = client.get("/api/v1/public/ping")
    assert first.status_code == 200
    assert first.headers["x-ratelimit-remaining"] == "0"
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) > 0


class FakeRedis:
    def __init__(self, result: list[int] | Exception) -> None:
        self.result = result
        self.keys: list[str] = []

    async def eval(self, _script: str, _key_count: int, key: str, *_args: object) -> list[int]:
        self.keys.append(key)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_redis_rate_limit_is_namespaced_atomic_and_fails_closed() -> None:
    redis = FakeRedis([1, 4, 0])
    limiter = RedisFixedWindowRateLimiter(redis, 5, 60, "synthetic")
    allowed = asyncio.run(limiter.check_async("public:client"))
    assert allowed.allowed is True
    assert allowed.remaining == 4
    assert redis.keys == ["synthetic:public:client"]

    unavailable = RedisFixedWindowRateLimiter(
        FakeRedis(RedisError("synthetic Redis outage")), 5, 60, "synthetic"
    )
    denied = asyncio.run(unavailable.check_async("auth:client"))
    assert denied.allowed is False
    assert denied.retry_after_seconds == 60


def test_metrics_are_disabled_by_default_and_token_protected_when_enabled() -> None:
    assert TestClient(create_app(Settings())).get("/api/v1/metrics").status_code == 503
    client = TestClient(
        create_app(Settings(metrics_token=SecretStr("synthetic-monitoring-token")))
    )
    client.get("/api/v1/health")
    assert client.get("/api/v1/metrics").status_code == 401
    metrics = client.get(
        "/api/v1/metrics",
        headers={"Authorization": "Bearer synthetic-monitoring-token"},
    )
    assert metrics.status_code == 200
    assert "somalia_ai_http_requests_total" in metrics.text
    assert 'route="/api/v1/health"' in metrics.text


def test_untrusted_request_id_is_not_reflected() -> None:
    assert safe_request_id("not-a-uuid") != "not-a-uuid"
    valid = "3f2f893d-72ac-4e67-a72d-ce525fd151a7"
    assert safe_request_id(valid) == valid


def test_production_rejects_development_secrets() -> None:
    with pytest.raises(ValueError, match="Production secrets"):
        Settings(environment="production")


def test_production_requires_distributed_rate_limit_backend() -> None:
    with pytest.raises(ValueError, match="Redis rate-limit"):
        Settings(
            environment="production",
            secret_key="production-secret-material-at-least-32-chars",
            s3_access_key="production-access-key",
            s3_secret_key="production-secret-key",
        )


def test_production_requires_https_notification_gateway() -> None:
    with pytest.raises(ValueError, match="notification gateway provider"):
        Settings(
            environment="production",
            secret_key="production-secret-material-at-least-32-chars",
            s3_access_key="production-access-key",
            s3_secret_key="production-secret-key",
            rate_limit_backend="redis",
        )
    with pytest.raises(ValueError, match="must use HTTPS"):
        Settings(
            environment="production",
            secret_key="production-secret-material-at-least-32-chars",
            s3_access_key="production-access-key",
            s3_secret_key="production-secret-key",
            rate_limit_backend="redis",
            notification_provider="gateway",
            notification_gateway_url="http://notifications.invalid",
            notification_gateway_token=SecretStr("synthetic-token"),
        )


def test_readiness_fails_closed_when_database_is_unavailable() -> None:
    unavailable = create_app(Settings())

    def failing_database() -> Generator[FailingDatabase, None, None]:
        yield FailingDatabase()

    unavailable.dependency_overrides[get_db] = failing_database
    response = TestClient(unavailable).get("/api/v1/readiness")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unavailable"}
