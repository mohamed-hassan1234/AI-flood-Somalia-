from time import perf_counter
from uuid import UUID, uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.core.observability import RateLimiter, RequestMetrics

logger = structlog.get_logger()


def safe_request_id(value: str | None) -> str:
    if value:
        try:
            return str(UUID(value))
        except ValueError:
            pass
    return str(uuid4())


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = safe_request_id(request.headers.get("x-request-id"))
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        response.headers["referrer-policy"] = "no-referrer"
        if "content-security-policy" not in response.headers:
            response.headers["content-security-policy"] = (
                "default-src 'none'; frame-ancestors 'none'"
            )
        return response


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, metrics: RequestMetrics) -> None:
        super().__init__(app)
        self.metrics = metrics

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = perf_counter()
        response = await call_next(request)
        duration = perf_counter() - started
        route_object = request.scope.get("route")
        route = getattr(route_object, "path", "unmatched")
        if request.url.path != "/api/v1/metrics":
            self.metrics.observe(request.method, route, response.status_code, duration)
        logger.info(
            "http_request",
            request_id=response.headers.get("x-request-id"),
            method=request.method,
            route=route,
            status_code=response.status_code,
            duration_ms=round(duration * 1000, 3),
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        auth_limiter: RateLimiter,
        public_limiter: RateLimiter,
    ) -> None:
        super().__init__(app)
        self.auth_limiter = auth_limiter
        self.public_limiter = public_limiter

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        limiter = None
        bucket = ""
        if path == "/api/v1/auth/login" or path == "/api/v1/auth/refresh":
            limiter, bucket = self.auth_limiter, "auth"
        elif path.startswith("/api/v1/public/"):
            limiter, bucket = self.public_limiter, "public"
        if limiter is None:
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        decision = await limiter.check_async(f"{bucket}:{client}")
        headers = {
            "x-ratelimit-limit": str(decision.limit),
            "x-ratelimit-remaining": str(decision.remaining),
        }
        if not decision.allowed:
            headers["retry-after"] = str(decision.retry_after_seconds)
            return JSONResponse(
                {"detail": "Rate limit exceeded"},
                status_code=429,
                headers=headers,
            )
        response = await call_next(request)
        response.headers.update(headers)
        return response
