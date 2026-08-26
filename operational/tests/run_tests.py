from __future__ import annotations

import time
import unittest
from pathlib import Path

from ml.common import now, write_json

ROOT = Path(__file__).resolve().parents[2]
PHASE03_VERSION = "1.0.0"


def main() -> int:
    started = time.perf_counter()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "operational" / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {
        "generated_at": now(),
        "phase03_version": PHASE03_VERSION,
        "status": "PASS" if result.wasSuccessful() else "FAIL",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "duration_seconds": time.perf_counter() - started,
    }
    write_json(ROOT / "data" / "metadata" / "phase03_test_report.json", report)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
