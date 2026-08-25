from pydantic import SecretStr
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.db.models.core import Alert, Membership, User
from app.db.seed import ROLE_EMAILS, SYNTHETIC_LABEL, seed_development


def test_development_seed_is_labelled_complete_and_idempotent() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        first = seed_development(db, Settings(environment="test"), "synthetic password only")
        second = seed_development(db, Settings(environment="test"), "synthetic password only")
        assert first.created_users == len(ROLE_EMAILS)
        assert second.created_users == 0
        assert db.scalar(select(func.count()).select_from(User)) == len(ROLE_EMAILS)
        assert db.scalar(select(func.count()).select_from(Membership)) == len(ROLE_EMAILS)
        alert = db.scalar(select(Alert).where(Alert.id == first.synthetic_alert_id))
        assert alert is not None
        assert SYNTHETIC_LABEL in alert.title
    engine.dispose()


def test_development_seed_refuses_production() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    production = Settings(
        environment="production",
        secret_key="production-secret-material-at-least-32-chars",
        s3_access_key="production-access-key",
        s3_secret_key="production-secret-key",
        rate_limit_backend="redis",
        notification_provider="gateway",
        notification_gateway_url="https://notifications.production.invalid",
        notification_gateway_token=SecretStr("production-notification-token"),
    )
    with Session(engine) as db:
        try:
            seed_development(db, production, "synthetic password only")
        except RuntimeError as exc:
            assert "disabled" in str(exc)
        else:
            raise AssertionError("Production seed must be rejected")
    engine.dispose()
