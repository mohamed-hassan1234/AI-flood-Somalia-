from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class HealthStatus(str, Enum):
    FRESH = "fresh"
    DELAYED = "delayed"
    STALE = "stale"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SourceHealth:
    status: HealthStatus
    age_seconds: float | None
    missing_fraction: float | None
    quarantined_rows: int


def assess_health(
    now: datetime,
    last_success: datetime | None,
    expected_frequency: timedelta,
    failed_since_success: bool,
    missing_fraction: float | None,
    quarantined_rows: int,
) -> SourceHealth:
    if last_success is None:
        return SourceHealth(
            HealthStatus.FAILED if failed_since_success else HealthStatus.UNKNOWN,
            None,
            missing_fraction,
            quarantined_rows,
        )
    if now.tzinfo is not None and last_success.tzinfo is None:
        last_success = last_success.replace(tzinfo=now.tzinfo)
    age = (now - last_success).total_seconds()
    status = (
        HealthStatus.FAILED
        if failed_since_success
        else HealthStatus.FRESH
        if age <= expected_frequency.total_seconds()
        else HealthStatus.DELAYED
        if age <= expected_frequency.total_seconds() * 2
        else HealthStatus.STALE
    )
    return SourceHealth(status, age, missing_fraction, quarantined_rows)
