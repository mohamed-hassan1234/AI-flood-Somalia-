from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.core import AuditEvent, SeasonDefinition
from app.db.session import get_db
from app.modules.auth.dependencies import Principal, get_current_principal, grants_for
from app.modules.seasons.schemas import SeasonCreate, SeasonResponse

router = APIRouter(prefix="/seasons", tags=["seasons"])


@router.post("", response_model=SeasonResponse, status_code=status.HTTP_201_CREATED)
def create_season(
    body: SeasonCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> SeasonDefinition:
    grants_for(principal, "seasons.manage")
    season = SeasonDefinition(**body.model_dump(), approved=False, active=True)
    db.add(season)
    db.flush()
    db.add(
        AuditEvent(
            id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_id=principal.user_id,
            action="seasons.create", entity_type="season_definition", entity_id=season.id,
            details={"version": season.version},
        )
    )
    db.commit()
    db.refresh(season)
    return season


@router.post("/{season_id}/approval", response_model=SeasonResponse)
def approve_season(
    season_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> SeasonDefinition:
    grants_for(principal, "seasons.approve")
    season = db.get(SeasonDefinition, season_id)
    if season is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Season definition not found")
    overlap = db.scalar(
        select(SeasonDefinition.id).where(
            SeasonDefinition.id != season.id,
            SeasonDefinition.approved.is_(True),
            SeasonDefinition.active.is_(True),
            SeasonDefinition.start <= season.end,
            SeasonDefinition.end >= season.start,
        )
    )
    if overlap:
        raise HTTPException(status.HTTP_409_CONFLICT, "Approved season windows cannot overlap")
    season.approved = True
    season.approved_by = principal.user_id
    db.add(
        AuditEvent(
            id=uuid4(), occurred_at=datetime.now(timezone.utc), actor_id=principal.user_id,
            action="seasons.approve", entity_type="season_definition", entity_id=season.id,
            details={"authority": season.authority, "version": season.version},
        )
    )
    db.commit()
    db.refresh(season)
    return season


@router.get("", response_model=list[SeasonResponse])
def list_seasons(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[SeasonDefinition]:
    grants_for(principal, "indicators.read")
    return list(
        db.scalars(
            select(SeasonDefinition)
            .where(SeasonDefinition.approved.is_(True), SeasonDefinition.active.is_(True))
            .order_by(SeasonDefinition.start)
        ).all()
    )
