import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
summary = json.loads((root / "ml/reports/phase02_run_summary.json").read_text(encoding="utf-8"))
for track, model in summary["models"].items():
    print(track.upper())
    for name, result in (("rule", model["baseline"]["rule"]["test"]), *[(key, value) for key, value in model["candidate_test_metrics"].items()]):
        print(name, *(f"{metric}={result[metric]:.6f}" for metric in ("pr_auc", "recall", "precision", "f1", "brier", "false_alarm_rate")))
    print("selected", model["selected_model"])
    print("calibration", model["calibration"])
    if "station_test_metrics" in model:
        for station, result in model["station_test_metrics"].items():
            print(station, *(f"{metric}={result[metric]:.6f}" for metric in ("pr_auc", "recall", "precision", "false_alarm_rate")))
