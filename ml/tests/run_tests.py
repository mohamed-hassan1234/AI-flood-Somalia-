from __future__ import annotations

import sys
import time
import unittest

from ml.common import now, write_json
from ml.pipeline import METADATA, ROOT, RUN_VERSION


def main() -> int:
    started = time.perf_counter()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "ml" / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {
        "generated_at": now(),
        "phase02_version": RUN_VERSION,
        "status": "PASS" if result.wasSuccessful() else "FAIL",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "duration_seconds": time.perf_counter() - started,
    }
    write_json(METADATA / "phase02_test_report.json", report)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
