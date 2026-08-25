from datetime import datetime, timedelta, timezone

from app.core.enums import RiskDomain, RiskLevel
from app.db.models.core import RiskSignal
from app.modules.dashboard.schemas import NationalDomainSummary

LEVEL_RANK = {
    RiskLevel.NORMAL: 0,
    RiskLevel.WATCH: 1,
    RiskLevel.WARNING: 2,
    RiskLevel.CRITICAL: 3,
}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def summarize_domains(
    signals: list[RiskSignal], now: datetime, stale_after: timedelta
) -> list[NationalDomainSummary]:
    summaries: list[NationalDomainSummary] = []
    for domain in RiskDomain:
        rows = [signal for signal in signals if signal.domain is domain]
        if not rows:
            summaries.append(
                NationalDomainSummary(
                    domain=domain,
                    level=None,
                    admin_units_evaluated=0,
                    target_periods=[],
                    source_ids=[],
                    as_of=None,
                    stale=True,
                )
            )
            continue
        as_of = max(_aware(signal.created_at) for signal in rows)
        source_ids = {
            str(driver["source_id"])
            for signal in rows
            for driver in signal.drivers
            if driver.get("source_id")
        }
        summaries.append(
            NationalDomainSummary(
                domain=domain,
                level=max((signal.level for signal in rows), key=LEVEL_RANK.__getitem__),
                admin_units_evaluated=len({signal.admin_unit_id for signal in rows}),
                target_periods=sorted({signal.target_period for signal in rows}),
                source_ids=sorted(source_ids),
                as_of=as_of,
                stale=now - as_of > stale_after,
            )
        )
    return summaries
