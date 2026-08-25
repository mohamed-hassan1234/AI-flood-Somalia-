from hmac import compare_digest
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Response, status
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.router import router
from app.core.config import Settings, get_settings
from app.core.middleware import (
    RateLimitMiddleware,
    RequestObservabilityMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.observability import (
    FixedWindowRateLimiter,
    RateLimiter,
    RedisFixedWindowRateLimiter,
    RequestMetrics,
)
from app.db.session import get_db


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Somalia AI Early Warning API", version="0.1.0")
    metrics = RequestMetrics()
    auth_limiter: RateLimiter
    public_limiter: RateLimiter
    if settings.rate_limit_backend == "redis":
        redis = Redis.from_url(settings.redis_url)
        auth_limiter = RedisFixedWindowRateLimiter(
            redis, settings.auth_rate_limit_per_minute, 60, "somalia-ai:rate-limit"
        )
        public_limiter = RedisFixedWindowRateLimiter(
            redis, settings.public_rate_limit_per_minute, 60, "somalia-ai:rate-limit"
        )
    else:
        auth_limiter = FixedWindowRateLimiter(settings.auth_rate_limit_per_minute, 60)
        public_limiter = FixedWindowRateLimiter(settings.public_rate_limit_per_minute, 60)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestObservabilityMiddleware, metrics=metrics)
    app.add_middleware(
        RateLimitMiddleware,
        auth_limiter=auth_limiter,
        public_limiter=public_limiter,
    )

    @app.get(f"{settings.api_v1_prefix}/health", tags=["operations"])
    def health() -> dict[str, str]:
        return {"status": "healthy"}

    @app.get(f"{settings.api_v1_prefix}/readiness", tags=["operations"])
    def readiness(
        response: Response,
        db: Annotated[Session, Depends(get_db)],
    ) -> dict[str, str]:
        try:
            db.execute(text("SELECT 1"))
        except SQLAlchemyError:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "not_ready", "database": "unavailable"}
        return {"status": "ready", "database": "available"}

    @app.get(f"{settings.api_v1_prefix}/metrics", tags=["operations"])
    def prometheus_metrics(
        authorization: Annotated[str | None, Header()] = None,
    ) -> Response:
        if settings.metrics_token is None:
            return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
        expected = f"Bearer {settings.metrics_token.get_secret_value()}"
        if authorization is None or not compare_digest(authorization, expected):
            return Response(status_code=status.HTTP_401_UNAUTHORIZED)
        return Response(metrics.render(), media_type="text/plain; version=0.0.4")

    app.include_router(router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
