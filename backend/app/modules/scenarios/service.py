from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioResult:
    label: str
    baseline_score: float
    simulated_score: float
    modifications: dict[str, float]
    may_publish_warning: bool = False


def simulate_linear(baseline_score: float, modifications: dict[str, float]) -> ScenarioResult:
    if not 0 <= baseline_score <= 1:
        raise ValueError("Baseline score must be normalized")
    simulated = min(1.0, max(0.0, baseline_score + sum(modifications.values())))
    return ScenarioResult("SIMULATION", baseline_score, round(simulated, 4), modifications)
