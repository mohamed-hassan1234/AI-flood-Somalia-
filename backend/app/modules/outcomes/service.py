from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean

from app.ml.evaluation import binary_metrics


@dataclass(frozen=True)
class EvaluationRow:
    observed: int
    probability: float
    predicted_at: datetime
    observed_at: datetime
    region: str
    season: str
    forecast_horizon_days: int


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _metric_block(rows: list[EvaluationRow]) -> dict[str, object]:
    metrics: dict[str, object] = {
        key: value
        for key, value in binary_metrics(
            [row.observed for row in rows], [row.probability for row in rows]
        ).items()
    }
    lead_times = [
        (aware(row.observed_at) - aware(row.predicted_at)).total_seconds() / 86400
        for row in rows
        if row.observed == 1
        and row.probability >= 0.5
        and aware(row.observed_at) >= aware(row.predicted_at)
    ]
    metrics["useful_lead_time_days"] = mean(lead_times) if lead_times else None
    return metrics


def summarize_evaluation(rows: list[EvaluationRow]) -> dict[str, object]:
    if not rows:
        raise ValueError("Evaluation requires at least one observed prediction")
    summary = _metric_block(rows)
    strata: list[dict[str, object]] = []
    dimensions = {
        "region": lambda row: row.region,
        "season": lambda row: row.season,
        "forecast_horizon_days": lambda row: str(row.forecast_horizon_days),
    }
    for dimension, selector in dimensions.items():
        values = sorted({selector(row) for row in rows})
        for value in values:
            group = [row for row in rows if selector(row) == value]
            strata.append(
                {
                    "dimension": dimension,
                    "value": value,
                    "sample_count": len(group),
                    **_metric_block(group),
                }
            )
    summary["strata"] = strata
    return summary
