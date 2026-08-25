from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Classification
from app.db.models.core import AdminUnit, Outcome, Prediction
from app.db.session import get_db
from app.modules.auth.dependencies import (
    Principal,
    get_current_principal,
    require_access,
)
from app.modules.outcomes.schemas import OutcomeCreate, OutcomeMetricsResponse, OutcomeResponse
from app.modules.outcomes.service import EvaluationRow, aware, summarize_evaluation

router = APIRouter(prefix="/outcomes", tags=["outcomes"])


@router.post("", response_model=OutcomeResponse, status_code=status.HTTP_201_CREATED)
def record_outcome(
    body: OutcomeCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Outcome:
    prediction = db.get(Prediction, body.prediction_id)
    if prediction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prediction not found")
    require_access(principal, "outcomes.manage", Classification.INTERNAL, prediction.admin_unit_id)
    if not body.source_lineage:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Outcome requires source lineage")
    if aware(body.observed_at) < aware(prediction.created_at):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Observed outcome cannot predate its prediction",
        )
    if db.scalar(select(Outcome.id).where(Outcome.prediction_id == prediction.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Outcome already recorded")
    outcome = Outcome(**body.model_dump())
    db.add(outcome)
    db.commit()
    db.refresh(outcome)
    return outcome


@router.get("/models/{model_version_id}/metrics", response_model=OutcomeMetricsResponse)
def model_outcome_metrics(
    model_version_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> OutcomeMetricsResponse:
    if "models.evaluate" not in principal.capabilities:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing capability: models.evaluate")
    rows = db.execute(
        select(Prediction, Outcome)
        .join(Outcome, Outcome.prediction_id == Prediction.id)
        .where(Prediction.model_version_id == model_version_id)
    ).all()
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No observed outcomes are available")
    units = {unit.id: unit for unit in db.scalars(select(AdminUnit)).all()}
    grants = [
        grant
        for grant in principal.grants
        if "models.evaluate" in grant.capabilities
        and grant.classification_ceiling is Classification.INTERNAL
    ]
    allowed = (
        set(units)
        if any(grant.national for grant in grants)
        else {unit_id for grant in grants for unit_id in grant.admin_unit_ids}
    )
    changed = True
    while changed:
        before = len(allowed)
        allowed.update(unit.id for unit in units.values() if unit.parent_id in allowed)
        changed = len(allowed) != before
    rows = [row for row in rows if row[0].admin_unit_id in allowed]
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No observed outcomes are available")
    evaluation_rows: list[EvaluationRow] = []
    for prediction, outcome in rows:
        unit = units.get(prediction.admin_unit_id)
        parent = units.get(unit.parent_id) if unit and unit.parent_id else None
        region = (
            unit.name
            if unit and unit.level == "region"
            else parent.name
            if parent and parent.level == "region"
            else "National / unclassified region"
        )
        evaluation_rows.append(
            EvaluationRow(
                observed=int(outcome.observed),
                probability=prediction.probability,
                predicted_at=prediction.created_at,
                observed_at=outcome.observed_at,
                region=region,
                season=prediction.target_period,
                forecast_horizon_days=prediction.forecast_horizon_days,
            )
        )
    summary = summarize_evaluation(evaluation_rows)
    predicted = [prediction.probability >= 0.5 for prediction, _ in rows]
    observed = [int(outcome.observed) for _, outcome in rows]
    return OutcomeMetricsResponse.model_validate(
        {
            "model_version_id": model_version_id,
            "sample_count": len(rows),
            **summary,
            "false_positives": sum(
                int(flag and not truth) for flag, truth in zip(predicted, observed)
            ),
            "missed_events": sum(
                int(not flag and truth) for flag, truth in zip(predicted, observed)
            ),
        }
    )
