import json
import os

from app.core.config import get_settings
from app.db.seed import seed_development
from app.db.session import SessionLocal


def main() -> None:
    password = os.environ.get("SEED_PASSWORD")
    if password is None:
        raise SystemExit("SEED_PASSWORD is required and must contain at least 12 characters")
    with SessionLocal() as db:
        result = seed_development(db, get_settings(), password)
    print(
        json.dumps(
            {
                "created_users": result.created_users,
                "accounts": result.accounts,
                "synthetic_alert_id": str(result.synthetic_alert_id),
                "password": "supplied through SEED_PASSWORD; never printed",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
