"""Repeatable synthetic core-path benchmark; never uses or claims production data."""

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from statistics import median
from time import perf_counter
from uuid import uuid4

from app.core.enums import RiskDomain, RiskLevel
from app.db.models.core import RiskSignal
from app.ml.evaluation import binary_metrics
from app.modules.dashboard.service import summarize_domains
from app.modules.ingestion.csv_adapter import parse_observation_csv

ROWS = 10_000
REPEATS = 5


def elapsed_ms(operation: Callable[[], object]) -> float:
    samples: list[float] = []
    for _ in range(REPEATS):
        started = perf_counter()
        operation()
        samples.append((perf_counter() - started) * 1000)
    return median(samples)


def main() -> None:
    header = "source_record_id,admin_unit_code,indicator_code,value,unit,reference_time\n"
    csv_body = header + "".join(
        f"r{index},SO-SYN,drought.rainfall_deficit,0.5,index_0_1,2027-01-01T00:00:00Z\n"
        for index in range(ROWS)
    )
    now = datetime.now(timezone.utc)
    signals = [
        RiskSignal(
            id=uuid4(),
            domain=list(RiskDomain)[index % len(RiskDomain)],
            admin_unit_id=uuid4(),
            level=list(RiskLevel)[index % len(RiskLevel)],
            score=0.5,
            confidence=0.8,
            drivers=[{"source_id": "synthetic-source"}],
            provenance={"label": "SYNTHETIC / DEVELOPMENT DATA"},
            target_period="2027-Gu",
            created_at=now,
        )
        for index in range(ROWS)
    ]
    observed = [index % 2 for index in range(ROWS)]
    probabilities = [0.8 if value else 0.2 for value in observed]
    results = {
        "label": "SYNTHETIC / DEVELOPMENT DATA",
        "rows_per_operation": ROWS,
        "repeats": REPEATS,
        "median_ms": {
            "csv_parse": round(elapsed_ms(lambda: parse_observation_csv(csv_body)), 3),
            "national_domain_aggregation": round(
                elapsed_ms(lambda: summarize_domains(signals, now, timedelta(hours=24))), 3
            ),
            "binary_outcome_metrics": round(
                elapsed_ms(lambda: binary_metrics(observed, probabilities)), 3
            ),
        },
    }
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
