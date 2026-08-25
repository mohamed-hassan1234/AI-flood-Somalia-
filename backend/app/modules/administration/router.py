from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import Classification
from app.db.models.core import (
    AdminUnit,
    AuditEvent,
    GeographicScope,
    Membership,
    Organization,
    Role,
    User,
)
from app.db.session import get_db
from app.modules.administration.schemas import (
    MembershipCreate,
    MembershipResponse,
    OrganizationCreate,
    OrganizationResponse,
    RoleResponse,
    UserCreate,
    UserResponse,
)
from app.modules.auth.dependencies import Principal, get_current_principal, grants_for
from app.modules.auth.security import hash_password

router = APIRouter(prefix="/administration", tags=["administration"])

_CLASSIFICATION_RANK = {
    Classification.PUBLIC: 0,
    Classification.PARTNER: 1,
    Classification.INTERNAL: 2,
}


def _national_grants(principal: Principal, capability: str):
    grants = tuple(grant for grant in grants_for(principal, capability) if grant.national)
    if not grants:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "National administrative scope required")
    return grants


def _audit(
    db: Session, principal: Principal, action: str, entity_type: str, entity_id: UUID
) -> None:
    db.add(
        AuditEvent(
            id=uuid4(),
            occurred_at=datetime.now(timezone.utc),
            actor_id=principal.user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details={},
        )
    )


@router.get("/organizations", response_model=list[OrganizationResponse])
def list_organizations(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Organization]:
    _national_grants(principal, "organizations.manage")
    return list(db.scalars(select(Organization).order_by(Organization.name)).all())


@router.post(
    "/organizations", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED
)
def create_organization(
    body: OrganizationCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Organization:
    _national_grants(principal, "organizations.manage")
    organization = Organization(**body.model_dump(), active=True)
    db.add(organization)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Organization name already exists") from exc
    _audit(db, principal, "organizations.create", "organization", organization.id)
    db.commit()
    db.refresh(organization)
    return organization


@router.get("/users", response_model=list[UserResponse])
def list_users(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[User]:
    _national_grants(principal, "users.manage")
    return list(db.scalars(select(User).order_by(User.email)).all())


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    _national_grants(principal, "users.manage")
    user = User(
        email=str(body.email).lower(),
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        active=True,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "User email already exists") from exc
    _audit(db, principal, "users.create", "user", user.id)
    db.commit()
    db.refresh(user)
    return user


@router.get("/roles", response_model=list[RoleResponse])
def list_roles(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Role]:
    _national_grants(principal, "users.manage")
    return list(db.scalars(select(Role).order_by(Role.name)).all())


@router.post("/memberships", response_model=MembershipResponse, status_code=status.HTTP_201_CREATED)
def create_membership(
    body: MembershipCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> MembershipResponse:
    grants = _national_grants(principal, "users.manage")
    if not any(
        _CLASSIFICATION_RANK[grant.classification_ceiling]
        >= _CLASSIFICATION_RANK[body.classification_ceiling]
        for grant in grants
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Classification assignment exceeds scope")
    user = db.get(User, body.user_id)
    organization = db.get(Organization, body.organization_id)
    role = db.get(Role, body.role_id)
    if user is None or organization is None or role is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "User, organization, or role missing")
    if not set(role.capabilities).issubset(principal.capabilities):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Role assignment exceeds own capabilities")
    units = list(
        db.scalars(select(AdminUnit).where(AdminUnit.id.in_(body.admin_unit_ids))).all()
    )
    if len(units) != len(body.admin_unit_ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Administrative scope missing")
    membership = Membership(
        user_id=body.user_id,
        organization_id=body.organization_id,
        role_id=body.role_id,
        classification_ceiling=body.classification_ceiling,
        active=True,
    )
    db.add(membership)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Membership already exists") from exc
    scopes = [
        GeographicScope(membership_id=membership.id, national=True)
        if body.national
        else GeographicScope(membership_id=membership.id, admin_unit_id=unit_id, national=False)
        for unit_id in ([None] if body.national else body.admin_unit_ids)
    ]
    db.add_all(scopes)
    _audit(db, principal, "memberships.create", "membership", membership.id)
    db.commit()
    return MembershipResponse(
        id=membership.id,
        user_id=membership.user_id,
        organization_id=membership.organization_id,
        role_id=membership.role_id,
        classification_ceiling=membership.classification_ceiling,
        active=membership.active,
        national=body.national,
        admin_unit_ids=body.admin_unit_ids,
    )


@router.get("/memberships", response_model=list[MembershipResponse])
def list_memberships(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[MembershipResponse]:
    _national_grants(principal, "users.manage")
    memberships = list(db.scalars(select(Membership).order_by(Membership.created_at)).all())
    scopes = list(db.scalars(select(GeographicScope)).all())
    by_membership: dict[UUID, list[GeographicScope]] = {}
    for scope in scopes:
        by_membership.setdefault(scope.membership_id, []).append(scope)
    return [
        MembershipResponse(
            id=membership.id,
            user_id=membership.user_id,
            organization_id=membership.organization_id,
            role_id=membership.role_id,
            classification_ceiling=membership.classification_ceiling,
            active=membership.active,
            national=any(scope.national for scope in by_membership.get(membership.id, [])),
            admin_unit_ids=[
                scope.admin_unit_id
                for scope in by_membership.get(membership.id, [])
                if scope.admin_unit_id is not None
            ],
        )
        for membership in memberships
    ]
