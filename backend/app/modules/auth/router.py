from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models.core import RefreshToken, User
from app.db.session import get_db
from app.modules.auth.dependencies import Principal, get_current_principal
from app.modules.auth.schemas import LoginRequest, PrincipalResponse, RefreshRequest, TokenResponse
from app.modules.auth.security import issue_access_token, token_fingerprint, verify_password

router = APIRouter(prefix="/auth", tags=["authentication"])


def _issue_pair(db: Session, user: User, settings: Settings) -> TokenResponse:
    raw_refresh = token_urlsafe(48)
    db.add(
        RefreshToken(
            token_hash=token_fingerprint(raw_refresh),
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
    )
    db.commit()
    return TokenResponse(
        access_token=issue_access_token(user.id, settings), refresh_token=raw_refresh
    )


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == body.email.lower(), User.active.is_(True)))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return _issue_pair(db, user, settings)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    body: RefreshRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    record = db.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_fingerprint(body.refresh_token),
            RefreshToken.revoked_at.is_(None),
        )
    )
    now = datetime.now(timezone.utc)
    expires_at = (
        record.expires_at.replace(tzinfo=timezone.utc)
        if record and record.expires_at.tzinfo is None
        else record.expires_at
        if record
        else None
    )
    if record is None or expires_at is None or expires_at <= now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")
    user = db.get(User, record.user_id)
    if user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")
    record.revoked_at = now
    return _issue_pair(db, user, settings)


@router.get("/me", response_model=PrincipalResponse)
def me(principal: Annotated[Principal, Depends(get_current_principal)]) -> PrincipalResponse:
    return PrincipalResponse(
        user_id=str(principal.user_id),
        email=principal.email,
        display_name=principal.display_name,
        capabilities=sorted(principal.capabilities),
    )
