from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import Classification
from app.db.models.core import GeographicScope, Membership, Role, User
from app.db.session import get_db
from app.modules.auth.security import decode_access_token

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class MembershipGrant:
    membership_id: UUID
    organization_id: UUID
    capabilities: frozenset[str]
    classification_ceiling: Classification
    national: bool
    admin_unit_ids: frozenset[UUID]


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    email: str
    display_name: str
    grants: tuple[MembershipGrant, ...]

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset(capability for grant in self.grants for capability in grant.capabilities)


def grants_for(principal: Principal, capability: str) -> tuple[MembershipGrant, ...]:
    grants = tuple(grant for grant in principal.grants if capability in grant.capabilities)
    if not grants:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing capability: {capability}")
    return grants


_CLASSIFICATION_RANK = {
    Classification.PUBLIC: 0,
    Classification.PARTNER: 1,
    Classification.INTERNAL: 2,
}


def require_access(
    principal: Principal,
    capability: str,
    classification: Classification,
    admin_unit_id: UUID,
) -> None:
    if has_access(principal, capability, classification, admin_unit_id):
        return
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "Access exceeds membership geography or classification scope",
    )


def has_access(
    principal: Principal,
    capability: str,
    classification: Classification,
    admin_unit_id: UUID,
) -> bool:
    matching = tuple(grant for grant in principal.grants if capability in grant.capabilities)
    for grant in matching:
        classification_allowed = (
            _CLASSIFICATION_RANK[grant.classification_ceiling]
            >= _CLASSIFICATION_RANK[classification]
        )
        geography_allowed = grant.national or admin_unit_id in grant.admin_unit_ids
        if classification_allowed and geography_allowed:
            return True
    return False


def load_principal(db: Session, user_id: UUID) -> Principal | None:
    user = db.scalar(select(User).where(User.id == user_id, User.active.is_(True)))
    if user is None:
        return None
    memberships = db.execute(
        select(Membership, Role)
        .join(Role, Role.id == Membership.role_id)
        .where(Membership.user_id == user.id, Membership.active.is_(True))
    ).all()
    grants: list[MembershipGrant] = []
    for membership, role in memberships:
        scopes = db.scalars(
            select(GeographicScope).where(GeographicScope.membership_id == membership.id)
        ).all()
        grants.append(
            MembershipGrant(
                membership.id,
                membership.organization_id,
                frozenset(role.capabilities),
                membership.classification_ceiling,
                any(scope.national for scope in scopes),
                frozenset(scope.admin_unit_id for scope in scopes if scope.admin_unit_id),
            )
        )
    return Principal(user.id, user.email, user.display_name, tuple(grants))


def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired credentials")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    try:
        user_id = decode_access_token(credentials.credentials, settings)
    except (jwt.InvalidTokenError, ValueError):
        raise unauthorized from None
    principal = load_principal(db, user_id)
    if principal is None:
        raise unauthorized
    return principal
