from uuid import uuid4

import jwt
import pytest

from app.core.config import Settings
from app.core.enums import Classification
from app.modules.auth.policy import AccessContext, authorize
from app.modules.auth.roles import ROLE_CAPABILITIES
from app.modules.auth.security import (
    decode_access_token,
    hash_password,
    issue_access_token,
    verify_password,
)


def test_password_round_trip_and_wrong_password() -> None:
    encoded = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("incorrect password", encoded)


def test_short_password_is_rejected() -> None:
    with pytest.raises(ValueError):
        hash_password("too-short")


def test_access_token_is_typed_and_signed() -> None:
    settings = Settings(secret_key="a-secure-test-secret-that-is-long-enough")
    user_id = uuid4()
    assert decode_access_token(issue_access_token(user_id, settings), settings) == user_id
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(
            issue_access_token(user_id, settings),
            Settings(secret_key="another-secure-test-secret-long-enough"),
        )


def test_geography_and_classification_are_backend_enforced() -> None:
    district, other = uuid4(), uuid4()
    context = AccessContext(
        uuid4(),
        frozenset({"alerts.create"}),
        Classification.PARTNER,
        admin_unit_ids=frozenset({district}),
    )
    authorize(context, "alerts.create", Classification.PARTNER, district)
    with pytest.raises(PermissionError):
        authorize(context, "alerts.create", Classification.INTERNAL, district)
    with pytest.raises(PermissionError):
        authorize(context, "alerts.create", Classification.PARTNER, other)


def test_ml_role_cannot_publish_alerts() -> None:
    assert "alerts.publish" not in ROLE_CAPABILITIES["Data / ML Scientist"]
