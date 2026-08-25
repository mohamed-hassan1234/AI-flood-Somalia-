import pytest

from scripts.benchmark_http import PATHS, percentile, run_benchmark


def test_percentile_is_deterministic() -> None:
    assert percentile([5, 1, 3, 2, 4], 0.5) == 3
    assert percentile([5, 1, 3, 2, 4], 0.95) == 4
    assert percentile([], 0.95) == 0


def test_synthetic_http_database_benchmark_exercises_all_routes() -> None:
    result = run_benchmark(requests=len(PATHS), concurrency=2)
    assert result["label"] == "SYNTHETIC / DEVELOPMENT DATA"
    assert result["error_rate"] == 0
    assert set(result["routes"]) == {name for name, _ in PATHS}
    assert all(route["requests"] == 1 for route in result["routes"].values())
    assert result["operations"]["bulk_ingestion"]["accepted"] == 200
    assert result["operations"]["bulk_ingestion"]["quarantined"] == 0
    assert result["operations"]["batch_predictions"]["rows"] == 200


def test_benchmark_rejects_invalid_concurrency() -> None:
    with pytest.raises(ValueError):
        run_benchmark(requests=len(PATHS), concurrency=len(PATHS) + 1)


def test_benchmark_requires_every_route_to_be_exercised() -> None:
    with pytest.raises(ValueError, match="routes"):
        run_benchmark(requests=len(PATHS) - 1, concurrency=1)
