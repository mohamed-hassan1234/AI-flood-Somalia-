from datetime import date, datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.core import AdminUnit, BoundaryRevision
from app.db.session import get_db
from app.modules.auth.dependencies import Principal, get_current_principal, grants_for
from app.modules.geography.schemas import (
    AdminUnitResponse,
    BoundaryFeatureCollectionResponse,
    BoundaryImportRequest,
    BoundaryImportResponse,
    RasterGridRequest,
    ZonalStatisticsResponse,
)
from app.modules.geography.service import (
    BoundaryValidationError,
    contains_point,
    parse_feature,
    validate_hierarchy,
    zonal_statistics,
)

router = APIRouter(prefix="/geography", tags=["geography"])


@router.post("/boundaries/import", response_model=BoundaryImportResponse)
def import_boundaries(
    body: BoundaryImportRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> BoundaryImportResponse:
    grants_for(principal, "geography.manage")
    collection = body.feature_collection
    raw_features = collection.get("features")
    if collection.get("type") != "FeatureCollection" or not isinstance(raw_features, list):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Valid FeatureCollection required")
    try:
        features = [
            parse_feature(feature, version=body.version, source=body.source, valid_from=body.valid_from)
            for feature in raw_features
            if isinstance(feature, dict)
        ]
        if len(features) != len(raw_features) or not features:
            raise BoundaryValidationError("Every feature must be a non-empty GeoJSON object")
        validate_hierarchy(features)
    except BoundaryValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    existing = {
        unit.stable_code: unit
        for unit in db.scalars(
            select(AdminUnit).where(AdminUnit.stable_code.in_([item.stable_code for item in features]))
        ).all()
    }
    units: dict[str, AdminUnit] = {}
    promoted: set[str] = set()
    for feature in features:
        unit = existing.get(feature.stable_code)
        if unit is None:
            unit = AdminUnit(
                stable_code=feature.stable_code,
                name=feature.name,
                level=feature.level,
                boundary_version=feature.version,
                boundary_source=feature.source,
                valid_from=feature.valid_from,
                valid_to=None,
                aliases=list(feature.aliases),
                geometry=feature.geometry,
            )
            promoted.add(feature.stable_code)
        elif feature.valid_from >= unit.valid_from:
            unit.name = feature.name
            unit.level = feature.level
            unit.boundary_version = feature.version
            unit.boundary_source = feature.source
            unit.valid_from = feature.valid_from
            unit.valid_to = None
            unit.aliases = list(feature.aliases)
            unit.geometry = feature.geometry
            promoted.add(feature.stable_code)
        db.add(unit)
        units[feature.stable_code] = unit
    db.flush()
    for feature in features:
        unit = units[feature.stable_code]
        parent_id = units[feature.parent_code].id if feature.parent_code else None
        if feature.stable_code in promoted:
            unit.parent_id = parent_id
        revision = db.scalar(
            select(BoundaryRevision).where(
                BoundaryRevision.admin_unit_id == unit.id,
                BoundaryRevision.version == feature.version,
            )
        )
        if revision is None:
            same_date = db.scalar(
                select(BoundaryRevision).where(
                    BoundaryRevision.admin_unit_id == unit.id,
                    BoundaryRevision.valid_from == feature.valid_from,
                )
            )
            if same_date is not None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    f"A boundary revision already starts on {feature.valid_from}",
                )
            db.add(
                BoundaryRevision(
                    admin_unit_id=unit.id,
                    parent_admin_unit_id=parent_id,
                    version=feature.version,
                    source=feature.source,
                    valid_from=feature.valid_from,
                    valid_to=None,
                    geometry=feature.geometry,
                )
            )
        elif (
            revision.geometry != feature.geometry
            or revision.source != feature.source
            or revision.valid_from != feature.valid_from
            or revision.parent_admin_unit_id != parent_id
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Boundary revision {feature.version} is immutable for {feature.stable_code}",
            )
    db.flush()
    for unit in units.values():
        revisions = list(
            db.scalars(
                select(BoundaryRevision)
                .where(BoundaryRevision.admin_unit_id == unit.id)
                .order_by(BoundaryRevision.valid_from, BoundaryRevision.version)
            ).all()
        )
        for index, revision in enumerate(revisions):
            revision.valid_to = (
                revisions[index + 1].valid_from - timedelta(days=1)
                if index + 1 < len(revisions)
                else None
            )
    db.commit()
    return BoundaryImportResponse(imported=len(features), version=body.version)


@router.get("/boundaries", response_model=BoundaryFeatureCollectionResponse)
def list_boundaries(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    boundary_version: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
) -> BoundaryFeatureCollectionResponse:
    units = list(db.scalars(select(AdminUnit).order_by(AdminUnit.name)).all())
    allowed = accessible_ids(units, principal)
    if boundary_version is not None:
        revisions = {
            revision.admin_unit_id: revision
            for revision in db.scalars(
                select(BoundaryRevision).where(BoundaryRevision.version == boundary_version)
            ).all()
        }
        return BoundaryFeatureCollectionResponse(
            features=[
                {
                    "type": "Feature",
                    "id": str(unit.id),
                    "geometry": revisions[unit.id].geometry,
                    "properties": {
                        "stable_code": unit.stable_code,
                        "name": unit.name,
                        "level": unit.level,
                        "boundary_version": revisions[unit.id].version,
                        "boundary_source": revisions[unit.id].source,
                    },
                }
                for unit in units
                if unit.id in allowed and unit.id in revisions
            ]
        )
    return BoundaryFeatureCollectionResponse(
        features=[
            {
                "type": "Feature",
                "id": str(unit.id),
                "geometry": unit.geometry,
                "properties": {
                    "stable_code": unit.stable_code,
                    "name": unit.name,
                    "level": unit.level,
                    "boundary_version": unit.boundary_version,
                    "boundary_source": unit.boundary_source,
                },
            }
            for unit in units
            if unit.id in allowed and unit.geometry is not None
        ]
    )


def accessible_ids(units: list[AdminUnit], principal: Principal) -> set[UUID]:
    grants = grants_for(principal, "geography.read")
    if any(grant.national for grant in grants):
        return {unit.id for unit in units}
    allowed = {unit_id for grant in grants for unit_id in grant.admin_unit_ids}
    changed = True
    while changed:
        before = len(allowed)
        allowed.update(unit.id for unit in units if unit.parent_id in allowed)
        changed = len(allowed) != before
    return allowed


@router.get("/admin-units", response_model=list[AdminUnitResponse])
def list_admin_units(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    level: Annotated[str | None, Query(pattern="^(country|region|district)$")] = None,
) -> list[AdminUnit]:
    units = list(db.scalars(select(AdminUnit).order_by(AdminUnit.level, AdminUnit.name)).all())
    allowed = accessible_ids(units, principal)
    return [unit for unit in units if unit.id in allowed and (level is None or unit.level == level)]


@router.get("/resolve-point", response_model=AdminUnitResponse)
def resolve_point(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    latitude: Annotated[float, Query(ge=-90, le=90)],
    boundary_version: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    reference_date: date | None = None,
) -> AdminUnitResponse:
    effective_date = reference_date or datetime.now(timezone.utc).date()
    units = list(db.scalars(select(AdminUnit)).all())
    allowed = accessible_ids(units, principal)
    revisions = db.execute(
        select(AdminUnit, BoundaryRevision)
        .join(BoundaryRevision, BoundaryRevision.admin_unit_id == AdminUnit.id)
        .where(
            AdminUnit.level == "district",
            BoundaryRevision.valid_from <= effective_date,
            (BoundaryRevision.valid_to.is_(None) | (BoundaryRevision.valid_to >= effective_date)),
        )
    ).all()
    matches = [
        (unit, revision)
        for unit, revision in revisions
        if unit.id in allowed
        and (boundary_version is None or revision.version == boundary_version)
        and contains_point(revision.geometry, longitude, latitude)
    ]
    if not matches:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No accessible district contains point")
    if len(matches) > 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Point is ambiguous across governed district boundaries",
        )
    unit, revision = matches[0]
    return AdminUnitResponse(
        id=unit.id,
        stable_code=unit.stable_code,
        name=unit.name,
        level=unit.level,
        parent_id=revision.parent_admin_unit_id,
        boundary_version=revision.version,
        boundary_source=revision.source,
        valid_from=revision.valid_from,
        valid_to=revision.valid_to,
        aliases=unit.aliases,
    )


@router.post(
    "/admin-units/{admin_unit_id}/zonal-statistics",
    response_model=ZonalStatisticsResponse,
)
def calculate_zonal_statistics(
    admin_unit_id: UUID,
    body: RasterGridRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> ZonalStatisticsResponse:
    units = list(db.scalars(select(AdminUnit)).all())
    allowed = accessible_ids(units, principal)
    unit = next((item for item in units if item.id == admin_unit_id), None)
    if unit is None or unit.id not in allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Administrative unit not found")
    revision = db.scalar(
        select(BoundaryRevision)
        .where(
            BoundaryRevision.admin_unit_id == unit.id,
            *(
                [BoundaryRevision.version == body.boundary_version]
                if body.boundary_version
                else []
            ),
        )
        .order_by(BoundaryRevision.valid_from.desc())
    )
    if revision is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Boundary revision not found")
    try:
        result = zonal_statistics(
            revision.geometry,
            body.values,
            west=body.west,
            south=body.south,
            east=body.east,
            north=body.north,
        )
    except BoundaryValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return ZonalStatisticsResponse.model_validate(
        {
            "admin_unit_id": unit.id,
            "boundary_version": revision.version,
            **result,
        }
    )


@router.get("/admin-units/{admin_unit_id}", response_model=AdminUnitResponse)
def get_admin_unit(
    admin_unit_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> AdminUnit:
    units = list(db.scalars(select(AdminUnit)).all())
    allowed = accessible_ids(units, principal)
    unit = next((item for item in units if item.id == admin_unit_id), None)
    if unit is None or unit.id not in allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Administrative unit not found")
    return unit
