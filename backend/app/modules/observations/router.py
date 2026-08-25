from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.core import (
    AdminUnit,
    DataSource,
    IndicatorDefinition,
    Observation,
    SeasonDefinition,
)
from app.db.session import get_db
from app.modules.auth.dependencies import Principal, get_current_principal, has_access
from app.modules.geography.router import accessible_ids
from app.modules.observations.schemas import AggregatedObservationResponse, ObservationResponse

router = APIRouter(prefix="/observations", tags=["observations"])


def season_for_time(
    definitions: list[SeasonDefinition], reference_time: datetime
) -> SeasonDefinition | None:
    matches = [season for season in definitions if season.start <= reference_time.date() <= season.end]
    if len(matches) > 1:
        raise RuntimeError("Approved season definitions overlap")
    return matches[0] if matches else None


@router.get("/aggregate", response_model=list[AggregatedObservationResponse])
def aggregate_observations(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    admin_unit_id: UUID,
    indicator_code: Annotated[str | None, Query(max_length=120)] = None,
) -> list[AggregatedObservationResponse]:
    units = list(db.scalars(select(AdminUnit)).all())
    seasons = list(
        db.scalars(
            select(SeasonDefinition).where(
                SeasonDefinition.approved.is_(True), SeasonDefinition.active.is_(True)
            )
        ).all()
    )
    allowed = accessible_ids(units, principal)
    target = next((unit for unit in units if unit.id == admin_unit_id), None)
    if target is None or target.id not in allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Administrative unit not found")
    descendants = {target.id}
    changed = True
    while changed:
        before = len(descendants)
        descendants.update(unit.id for unit in units if unit.parent_id in descendants)
        changed = len(descendants) != before
    leaf_ids = {
        unit.id
        for unit in units
        if unit.id in descendants and not any(child.parent_id == unit.id for child in units)
    }
    statement = (
        select(Observation, DataSource)
        .join(DataSource, DataSource.id == Observation.source_id)
        .where(Observation.admin_unit_id.in_(leaf_ids))
        .order_by(Observation.reference_time)
    )
    if indicator_code:
        statement = statement.where(Observation.indicator_code == indicator_code)
    rows = [
        (observation, source)
        for observation, source in db.execute(statement).all()
        if has_access(
            principal, "indicators.read", source.classification, observation.admin_unit_id
        )
    ]
    grouped: dict[tuple[str, datetime, str], list[tuple[Observation, DataSource]]] = {}
    for observation, source in rows:
        grouped.setdefault(
            (observation.indicator_code, observation.reference_time, observation.unit), []
        ).append((observation, source))
    results: list[AggregatedObservationResponse] = []
    for (code, reference_time, unit), group in grouped.items():
        season = season_for_time(seasons, reference_time)
        values = [observation.value for observation, _ in group if observation.value is not None]
        contributors = {
            observation.admin_unit_id for observation, _ in group if observation.value is not None
        }
        sources = {source.id: source.name for _, source in group}
        results.append(
            AggregatedObservationResponse(
                admin_unit_id=target.id,
                indicator_code=code,
                reference_time=reference_time,
                latest_retrieved_at=max(observation.retrieved_at for observation, _ in group),
                season_name=season.name if season else None,
                season_version=season.version if season else None,
                season_authority=season.authority if season else None,
                value=round(sum(values) / len(values), 6) if values else None,
                unit=unit,
                method="unweighted_mean",
                contributing_admin_units=len(contributors),
                total_descendant_units=len(leaf_ids),
                missing_records=sum(observation.value is None for observation, _ in group),
                source_ids=sorted(sources),
                source_names=[sources[source_id] for source_id in sorted(sources)],
                boundary_version=target.boundary_version,
            )
        )
    return results


@router.get("", response_model=list[ObservationResponse])
def list_observations(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    admin_unit_id: UUID,
    indicator_code: Annotated[str | None, Query(max_length=120)] = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> list[ObservationResponse]:
    if start and end and start > end:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "start must not be after end")
    statement = (
        select(Observation, DataSource, IndicatorDefinition)
        .join(DataSource, DataSource.id == Observation.source_id)
        .outerjoin(IndicatorDefinition, IndicatorDefinition.id == Observation.indicator_definition_id)
        .where(Observation.admin_unit_id == admin_unit_id)
        .order_by(Observation.reference_time)
        .limit(limit)
    )
    if indicator_code:
        statement = statement.where(Observation.indicator_code == indicator_code)
    if start:
        statement = statement.where(Observation.reference_time >= start)
    if end:
        statement = statement.where(Observation.reference_time <= end)
    rows = db.execute(statement).all()
    seasons = list(
        db.scalars(
            select(SeasonDefinition).where(
                SeasonDefinition.approved.is_(True), SeasonDefinition.active.is_(True)
            )
        ).all()
    )
    visible = [
        (observation, source, definition)
        for observation, source, definition in rows
        if has_access(
            principal,
            "indicators.read",
            source.classification,
            observation.admin_unit_id,
        )
    ]
    if rows and not visible:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No observations are visible in this scope")
    return [
        ObservationResponse(
            id=observation.id,
            source_id=source.id,
            source_name=source.name,
            source_classification=source.classification,
            admin_unit_id=observation.admin_unit_id,
            indicator_code=observation.indicator_code,
            indicator_definition_id=definition.id if definition else None,
            indicator_version=definition.version if definition else None,
            season_name=(season.name if (season := season_for_time(seasons, observation.reference_time)) else None),
            season_version=season.version if season else None,
            season_authority=season.authority if season else None,
            value=observation.value,
            value_kind=observation.value_kind,
            unit=observation.unit,
            reference_time=observation.reference_time,
            retrieved_at=observation.retrieved_at,
            stage=observation.stage,
            quality_flags=observation.quality_flags,
            boundary_version=observation.boundary_version,
        )
        for observation, source, definition in visible
    ]
