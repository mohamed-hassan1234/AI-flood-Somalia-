# Synthetic core-path performance baseline

Measured 2026-08-23 on the local Windows development host with Python 3.13.5. Input is explicitly
`SYNTHETIC / DEVELOPMENT DATA`; five repetitions were run and the median recorded.

Command from `backend/`:

```shell
python -m scripts.benchmark_core
```

| Operation | Rows | Median |
|---|---:|---:|
| CSV parse and row validation | 10,000 | 49.970 ms |
| National four-domain aggregation | 10,000 | 29.272 ms |
| Binary outcome metrics | 10,000 | 19.534 ms |

These are local, in-process algorithm baselines—not production service-level objectives. They omit
MySQL query time, authorization joins, network/TLS, container scheduling, object storage, frontend
rendering, and concurrent load. Containerized HTTP/database load tests on representative approved
data are still required before release readiness can be claimed.

## Synthetic concurrent HTTP/database exercise

Measured 2026-08-23 on the same local development host:

```shell
python -m scripts.benchmark_http --requests 90 --concurrency 6 --max-p95-ms 2000 --max-operation-ms 5000 --max-error-rate 0
```

The run used the labelled development seed, an in-process ASGI transport, and a temporary SQLite
database. It completed 90 requests with concurrency 6 in 1.883 seconds (47.785 requests/second)
with zero HTTP errors.

| Route | Requests | p50 | p95 | Max |
|---|---:|---:|---:|---:|
| Readiness/database query | 10 | 37.667 ms | 64.635 ms | 222.736 ms |
| National summary | 10 | 72.940 ms | 109.736 ms | 342.899 ms |
| Boundary map layer | 10 | 67.118 ms | 97.483 ms | 311.103 ms |
| District time series (200 synthetic rows) | 10 | 541.584 ms | 644.942 ms | 659.129 ms |
| Scoped risk signals | 10 | 52.920 ms | 100.351 ms | 295.802 ms |
| Scoped alerts | 10 | 53.423 ms | 80.211 ms | 294.666 ms |
| Scoped reports | 10 | 54.121 ms | 90.126 ms | 128.982 ms |
| Public warnings | 10 | 37.745 ms | 45.589 ms | 67.698 ms |
| Public reports | 10 | 35.123 ms | 55.031 ms | 62.919 ms |

The same isolated run measured transactional database workloads:

| Operation | Rows | Duration | Throughput | Result |
|---|---:|---:|---:|---|
| Governed bulk observation ingestion | 200 | 673.393 ms | 297.003 rows/s | 200 accepted, 0 quarantined |
| Transparent baseline batch prediction persistence | 200 | 53.170 ms | 3,761.506 rows/s | 200 persisted |

CI repeats this exercise with deliberately generous ceilings of 2,000 ms per-route p95 and 5,000
ms per database workload, plus a zero-error requirement. That gate detects severe code-path regressions; it is not an SLO or a
production capacity result. It omits network/TLS, MySQL contention, Redis, multiple API workers,
large approved datasets, object storage, and container/orchestrator overhead. A containerized load
test using representative approved data is still required before release approval.
