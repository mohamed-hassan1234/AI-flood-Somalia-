from datetime import datetime, timedelta, timezone

from app.modules.data_sources.health import HealthStatus, assess_health


def test_health_distinguishes_unknown_failed_delayed_and_stale() -> None:
    now = datetime.now(timezone.utc)
    frequency = timedelta(hours=6)
    assert assess_health(now, None, frequency, False, None, 0).status is HealthStatus.UNKNOWN
    assert assess_health(now, None, frequency, True, None, 2).status is HealthStatus.FAILED
    assert (
        assess_health(now, now - timedelta(hours=8), frequency, False, 0.1, 0).status
        is HealthStatus.DELAYED
    )
    assert (
        assess_health(now, now - timedelta(hours=13), frequency, False, 0.1, 0).status
        is HealthStatus.STALE
    )
