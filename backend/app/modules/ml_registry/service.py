VALID_TRANSITIONS = {
    "candidate": {"validated", "retired"},
    "validated": {"production", "retired"},
    "production": {"validated", "retired"},
    "retired": set(),
}


def transition_model(
    current: str, target: str, metrics: dict[str, object], model_card: dict[str, object]
) -> str:
    if target not in VALID_TRANSITIONS.get(current, set()):
        raise ValueError(f"Model cannot transition from {current} to {target}")
    if target == "production":
        required_metrics = {
            "precision",
            "recall",
            "f1",
            "macro_f1",
            "pr_auc",
            "roc_auc",
            "brier",
            "calibration_error",
            "high_risk_recall",
            "useful_lead_time_days",
        }
        if not required_metrics.issubset(metrics):
            raise ValueError("Production promotion requires the complete governed metric set")
        required_evidence = [
            model_card.get("chronological_backtest") is True,
            model_card.get("region_evaluation") is True,
            model_card.get("season_evaluation") is True,
            model_card.get("horizon_evaluation") is True,
            model_card.get("calibration_evaluation") is True,
            model_card.get("lead_time_evaluation") is True,
            bool(model_card.get("limitations")),
        ]
        if not all(required_evidence):
            raise ValueError(
                "Production promotion requires chronological, regional, seasonal, and limitation evidence"
            )
    return target
