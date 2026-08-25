from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.core import IndicatorDefinition
from app.db.session import get_db
from app.modules.auth.dependencies import Principal, get_current_principal, grants_for
from app.modules.indicators.schemas import IndicatorCreate, IndicatorResponse

router = APIRouter(prefix="/indicators", tags=["indicators"])


@router.post("", response_model=IndicatorResponse, status_code=status.HTTP_201_CREATED)
def create_indicator(
    body: IndicatorCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> IndicatorDefinition:
    grants_for(principal, "indicators.manage")
    if db.scalar(select(IndicatorDefinition.id).where(IndicatorDefinition.code == body.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Indicator code already exists")
    indicator = IndicatorDefinition(**body.model_dump())
    db.add(indicator)
    db.commit()
    db.refresh(indicator)
    return indicator


@router.get("", response_model=list[IndicatorResponse])
def list_indicators(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[IndicatorDefinition]:
    grants_for(principal, "indicators.read")
    return list(db.scalars(select(IndicatorDefinition).order_by(IndicatorDefinition.code)).all())
