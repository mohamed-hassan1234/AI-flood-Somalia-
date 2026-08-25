from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Any, Protocol

from redis.exceptions import RedisError


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


class RateLimiter(Protocol):
    async def check_async(self, key: str) -> RateLimitDecision: ...


class FixedWindowRateLimiter:
    """Thread-safe process-local limiter used as a baseline and in tests."""

    def __init__(
        self,
        limit: int,
        window_seconds: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if limit < 1 or window_seconds < 1:
            raise ValueError("Rate limit and window must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> RateLimitDecision:
        now = self._clock()
        cutoff = now - self.window_seconds
        with self._lock:
            requests = self._requests[key]
            while requests and requests[0] <= cutoff:
                requests.popleft()
            if len(requests) >= self.limit:
                retry_after = max(1, int(self.window_seconds - (now - requests[0])))
                return RateLimitDecision(False, self.limit, 0, retry_after)
            requests.append(now)
            return RateLimitDecision(True, self.limit, self.limit - len(requests), 0)

    async def check_async(self, key: str) -> RateLimitDecision:
        return self.check(key)


class RedisFixedWindowRateLimiter:
    """Cluster-consistent fixed window implemented atomically in Redis."""

    _SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
local ttl = redis.call('TTL', KEYS[1])
if current > tonumber(ARGV[1]) then
  return {0, 0, math.max(ttl, 1)}
end
return {1, math.max(tonumber(ARGV[1]) - current, 0), 0}
"""

    def __init__(self, client: Any, limit: int, window_seconds: int, namespace: str) -> None:
        if limit < 1 or window_seconds < 1:
            raise ValueError("Rate limit and window must be positive")
        self.client = client
        self.limit = limit
        self.window_seconds = window_seconds
        self.namespace = namespace

    async def check_async(self, key: str) -> RateLimitDecision:
        try:
            raw = await self.client.eval(
                self._SCRIPT,
                1,
                f"{self.namespace}:{key}",
                str(self.limit),
                str(self.window_seconds),
            )
            allowed, remaining, retry_after = (int(value) for value in raw)
            return RateLimitDecision(
                bool(allowed), self.limit, remaining, retry_after
            )
        except RedisError:
            return RateLimitDecision(False, self.limit, 0, self.window_seconds)


class RequestMetrics:
    def __init__(self) -> None:
        self._counts: dict[tuple[str, str, int], int] = defaultdict(int)
        self._duration_seconds: dict[tuple[str, str], float] = defaultdict(float)
        self._lock = Lock()

    def observe(self, method: str, route: str, status_code: int, duration: float) -> None:
        with self._lock:
            self._counts[(method, route, status_code)] += 1
            self._duration_seconds[(method, route)] += duration

    def render(self) -> str:
        lines = [
            "# HELP somalia_ai_http_requests_total Total HTTP requests.",
            "# TYPE somalia_ai_http_requests_total counter",
        ]
        with self._lock:
            for (method, route, status_code), count in sorted(self._counts.items()):
                labels = f'method="{method}",route="{route}",status="{status_code}"'
                lines.append(f"somalia_ai_http_requests_total{{{labels}}} {count}")
            lines.extend(
                [
                    "# HELP somalia_ai_http_request_duration_seconds_sum HTTP request duration.",
                    "# TYPE somalia_ai_http_request_duration_seconds_sum counter",
                ]
            )
            for (method, route), duration in sorted(self._duration_seconds.items()):
                labels = f'method="{method}",route="{route}"'
                lines.append(
                    f"somalia_ai_http_request_duration_seconds_sum{{{labels}}} {duration:.6f}"
                )
        return "\n".join(lines) + "\n"
