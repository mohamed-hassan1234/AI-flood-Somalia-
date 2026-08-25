from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Classification, DataStage, RiskDomain
from app.db.models.core import AdminUnit, DataSource, Observation, RiskSignal
from app.db.session import get_db
from app.modules.auth.dependencies import (
    Principal,
    get_current_principal,
    grants_for,
    require_access,
)
from app.modules.risks.baseline import EvidenceValue, transparent_baseline
from app.modules.risks.domains import DOMAIN_FEATURES
from app.modules.risks.schemas import RiskEvaluationRequest, RiskSignalResponse

router = APIRouter(prefix="/risks", tags=["risk signals"])


def _prediction_scope(db: Session, principal: Principal) -> set[UUID]:
    units = list(db.scalars(select(AdminUnit)).all())
    grants = grants_for(principal, "predictions.read")
    if any(grant.national for grant in grants):
        return {unit.id for unit in units}
    allowed = {unit_id for grant in grants for unit_id in grant.admin_unit_ids}
    changed = True
    while changed:
        before = len(allowed)
        allowed.update(unit.id for unit in units if unit.parent_id in allowed)
        changed = len(allowed) != before
    return allowed


@router.get("", response_model=list[RiskSignalResponse])
def list_risk_signals(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    domain: RiskDomain | None = None,
    admin_unit_id: UUID | None = None,
    limit: int = 200,
) -> list[RiskSignal]:
    if limit < 1 or limit > 1000:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "limit must be between 1 and 1000"
        )
    allowed = _prediction_scope(db, principal)
    statement = (
        select(RiskSignal)
        .where(RiskSignal.admin_unit_id.in_(allowed))
        .order_by(RiskSignal.created_at.desc())
        .limit(limit)
    )
    if domain is not None:
        statement = statement.where(RiskSignal.domain == domain)
    if admin_unit_id is not None:
        if admin_unit_id not in allowed:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Risk scope not found")
        statement = statement.where(RiskSignal.admin_unit_id == admin_unit_id)
    return list(db.scalars(statement).all())


@router.post(
    "/{domain}/evaluations", response_model=RiskSignalResponse, status_code=status.HTTP_201_CREATED
)
def evaluate(
    domain: RiskDomain,
    body: RiskEvaluationRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> RiskSignal:
    require_access(principal, "predictions.generate", Classification.INTERNAL, body.admin_unit_id)
    feature_weights = DOMAIN_FEATURES[domain]
    rows = db.execute(
        select(Observation, DataSource)
        .join(DataSource, DataSource.id == Observation.source_id)
        .where(
            Observation.admin_unit_id == body.admin_unit_id,
            Observation.indicator_code.in_(feature_weights),
            Observation.stage == DataStage.NORMALIZED,
            DataSource.verified.is_(True),
        )
        .order_by(Observation.reference_time.desc(), Observation.retrieved_at.desc())
    ).all()
    if not rows:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Insufficient verified normalized evidence"
        )
    evaluation_at = body.evaluation_at or max(observation.reference_time for observation, _ in rows)
    if evaluation_at.tzinfo is None:
        evaluation_at = evaluation_at.replace(tzinfo=timezone.utc)
    cutoff = evaluation_at - timedelta(days=body.lookback_days)

    def utc(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    latest: dict[str, tuple[Observation, DataSource]] = {}
    for observation, source in rows:
        reference_time = utc(observation.reference_time)
        if cutoff <= reference_time <= evaluation_at:
            latest.setdefault(observation.indicator_code, (observation, source))
    evidence = [
        EvidenceValue(latest[code][0].value if code in latest else None, weight)
        for code, weight in feature_weights.items()
    ]
    try:
        result = transparent_baseline(evidence)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    if result.low_data or result.score is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Insufficient verified normalized evidence"
        )
    drivers = [
        {
            "indicator": code,
            "value": latest[code][0].value,
            "weight": weight,
            "observation_id": str(latest[code][0].id),
            "source_id": str(latest[code][1].id),
            "source_name": latest[code][1].name,
            "unit": latest[code][0].unit,
            "reference_time": utc(latest[code][0].reference_time).isoformat(),
            "retrieved_at": utc(latest[code][0].retrieved_at).isoformat(),
            "quality_flags": latest[code][0].quality_flags,
            "boundary_version": latest[code][0].boundary_version,
        }
        for code, weight in feature_weights.items()
        if code in latest
    ]
    signal = RiskSignal(
        domain=domain,
        admin_unit_id=body.admin_unit_id,
        level=result.level,
        score=result.score,
        confidence=result.completeness,
        drivers=drivers,
        provenance={
            "method": "transparent_weighted_baseline_v1",
            "verified_sources_only": True,
            "normalized_evidence_only": True,
            "automatic_warning_publication": False,
            "evaluation_at": evaluation_at.isoformat(),
            "lookback_days": body.lookback_days,
            "window_start": cutoff.isoformat(),
            "feature_weights": feature_weights,
            "score_thresholds": {"watch": 0.4, "warning": 0.6, "critical": 0.8},
            "minimum_weight_completeness": 0.5,
            "weight_completeness": result.completeness,
            "missing_indicators": sorted(set(feature_weights) - set(latest)),
            "source_ids": sorted({str(source.id) for _, source in latest.values()}),
        },
        target_period=body.target_period,
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)
    return signal
