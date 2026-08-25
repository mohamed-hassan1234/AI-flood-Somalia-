from dataclasses import dataclass

from app.core.enums import RiskLevel


@dataclass(frozen=True)
class EvidenceValue:
    value: float | None
    weight: float


@dataclass(frozen=True)
class BaselineResult:
    level: RiskLevel
    score: float | None
    completeness: float
    low_data: bool


def transparent_baseline(evidence: list[EvidenceValue]) -> BaselineResult:
    """Combine normalized approved evidence without treating missing values as zero."""
    if any(item.value is not None and not 0 <= item.value <= 1 for item in evidence):
        raise ValueError("Risk evidence must be normalized between 0 and 1")
    available = [(item.value, item.weight) for item in evidence if item.value is not None]
    total_weight = sum(item.weight for item in evidence)
    used_weight = sum(weight for _, weight in available)
    completeness = used_weight / total_weight if total_weight else 0.0
    if not available or completeness < 0.5:
        return BaselineResult(RiskLevel.NORMAL, None, completeness, True)
    score = sum(value * weight for value, weight in available) / used_weight
    level = (
        RiskLevel.CRITICAL
        if score >= 0.8
        else RiskLevel.WARNING
        if score >= 0.6
        else RiskLevel.WATCH
        if score >= 0.4
        else RiskLevel.NORMAL
    )
    return BaselineResult(level, round(score, 4), completeness, False)
