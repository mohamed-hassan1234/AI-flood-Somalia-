from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.core.config import Settings, get_settings
from app.core.enums import AlertStatus, Classification
from app.db.models.core import AdminUnit, Alert, RiskSignal
from app.db.session import get_db
from app.modules.auth.dependencies import Principal, get_current_principal, grants_for
from app.modules.dashboard.schemas import DashboardScopeResponse, NationalSummaryResponse
from app.modules.dashboard.service import summarize_domains

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _scope_ids(units: list[AdminUnit], roots: set[UUID]) -> set[UUID]:
    allowed = set(roots)
    changed = True
    while changed:
        before = len(allowed)
        allowed.update(unit.id for unit in units if unit.parent_id in allowed)
        changed = len(allowed) != before
    return allowed


def _prediction_scope(units: list[AdminUnit], principal: Principal) -> set[UUID]:
    grants = grants_for(principal, "predictions.read")
    if any(
        grant.national and grant.classification_ceiling is Classification.INTERNAL
        for grant in grants
    ):
        return {unit.id for unit in units}
    roots = {
        unit_id
        for grant in grants
        if grant.classification_ceiling is Classification.INTERNAL
        for unit_id in grant.admin_unit_ids
    }
    return _scope_ids(units, roots)


def _alert_scope(
    units: list[AdminUnit], principal: Principal, classification: Classification
) -> set[UUID]:
    rank = {Classification.PUBLIC: 0, Classification.PARTNER: 1, Classification.INTERNAL: 2}
    grants = [
        grant
        for grant in principal.grants
        if "alerts.read" in grant.capabilities
        if rank[grant.classification_ceiling] >= rank[classification]
    ]
    if any(grant.national for grant in grants):
        return {unit.id for unit in units}
    return _scope_ids(units, {unit_id for grant in grants for unit_id in grant.admin_unit_ids})


@router.get("/scopes", response_model=list[DashboardScopeResponse])
def dashboard_scopes(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[AdminUnit]:
    units = list(db.scalars(select(AdminUnit).order_by(AdminUnit.level, AdminUnit.name)).all())
    allowed = _prediction_scope(units, principal)
    return [unit for unit in units if unit.id in allowed]


@router.get("/national-summary", response_model=NationalSummaryResponse)
def national_summary(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    admin_unit_id: UUID | None = None,
) -> NationalSummaryResponse:
    units = list(db.scalars(select(AdminUnit)).all())
    allowed = _prediction_scope(units, principal)
    selected = next((unit for unit in units if unit.id == admin_unit_id), None)
    national_internal = any(
        grant.national and grant.classification_ceiling is Classification.INTERNAL
        for grant in grants_for(principal, "predictions.read")
    )
    if admin_unit_id is None and not national_internal:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "National dashboard requires national internal analytical scope",
        )
    if admin_unit_id is not None and (selected is None or selected.id not in allowed):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dashboard scope not found")
    included = {unit.id for unit in units} if selected is None else _scope_ids(units, {selected.id})
    previous = aliased(RiskSignal)
    latest_time = (
        select(func.max(previous.created_at))
        .where(
            previous.domain == RiskSignal.domain,
            previous.admin_unit_id == RiskSignal.admin_unit_id,
        )
        .correlate(RiskSignal)
        .scalar_subquery()
    )
    signals = list(
        db.scalars(select(RiskSignal).where(RiskSignal.created_at == latest_time)).all()
    )
    signals = [
        signal
        for signal in signals
        if signal.admin_unit_id in allowed and signal.admin_unit_id in included
    ]
    published_rows = db.execute(
        select(Alert, RiskSignal)
        .join(RiskSignal, RiskSignal.id == Alert.signal_id)
        .where(Alert.status == AlertStatus.PUBLISHED)
    ).all()
    published_warning_count = sum(
        1
        for alert, signal in published_rows
        if signal.admin_unit_id in included
        and signal.admin_unit_id in _alert_scope(units, principal, alert.classification)
    )
    now = datetime.now(timezone.utc)
    return NationalSummaryResponse(
        generated_at=now,
        boundary_scope=(
            "versioned national aggregation"
            if selected is None
            else f"versioned {selected.level} aggregation"
        ),
        scope_admin_unit_id=selected.id if selected else None,
        scope_name=selected.name if selected else "Somalia",
        scope_level=selected.level if selected else "country",
        boundary_version=selected.boundary_version if selected else None,
        published_warning_count=published_warning_count,
        domains=summarize_domains(
            signals,
            now,
            timedelta(hours=settings.dashboard_stale_after_hours),
        ),
    )
