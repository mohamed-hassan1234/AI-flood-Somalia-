from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Classification
from app.db.models.core import AdminUnit, DatasetSnapshot, Scenario
from app.db.session import get_db
from app.modules.auth.dependencies import (
    Principal,
    get_current_principal,
    has_access,
    require_access,
)
from app.modules.scenarios.schemas import ScenarioCreate, ScenarioListResponse, ScenarioResponse
from app.modules.scenarios.service import simulate_linear

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("", response_model=list[ScenarioListResponse])
def list_scenarios(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ScenarioListResponse]:
    rows = db.execute(
        select(Scenario, DatasetSnapshot, AdminUnit)
        .join(DatasetSnapshot, DatasetSnapshot.id == Scenario.baseline_snapshot_id)
        .join(AdminUnit, AdminUnit.id == Scenario.admin_unit_id)
        .order_by(Scenario.created_at.desc())
    ).all()
    return [
        ScenarioListResponse(
            id=scenario.id,
            name=scenario.name,
            snapshot_name=snapshot.name,
            admin_unit_id=unit.id,
            admin_unit_name=unit.name,
            domain=scenario.domain,
            modifications=scenario.modifications,
            result=scenario.result,
            label=scenario.label,
            created_at=scenario.created_at,
        )
        for scenario, snapshot, unit in rows
        if has_access(
            principal, "scenarios.read", Classification.INTERNAL, scenario.admin_unit_id
        )
    ]


@router.post("", response_model=ScenarioResponse, status_code=status.HTTP_201_CREATED)
def create_scenario(
    body: ScenarioCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Scenario:
    require_access(principal, "scenarios.run", Classification.INTERNAL, body.admin_unit_id)
    if db.get(DatasetSnapshot, body.baseline_snapshot_id) is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Baseline snapshot does not exist"
        )
    result = simulate_linear(body.baseline_score, body.modifications)
    scenario = Scenario(
        name=body.name,
        baseline_snapshot_id=body.baseline_snapshot_id,
        admin_unit_id=body.admin_unit_id,
        domain=body.domain,
        modifications=body.modifications,
        result={
            "baseline_score": result.baseline_score,
            "simulated_score": result.simulated_score,
            "may_publish_warning": result.may_publish_warning,
        },
        label="SIMULATION",
        created_by=principal.user_id,
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return scenario
