from dataclasses import dataclass
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import (
    ActionStatus,
    AlertStatus,
    Classification,
    DataStage,
    RiskDomain,
    RiskLevel,
)
from app.db.models.core import (
    ActionItem,
    ActionPlan,
    AdminUnit,
    Alert,
    DataSource,
    GeographicScope,
    Membership,
    Observation,
    Organization,
    Playbook,
    RiskSignal,
    Role,
    User,
)
from app.modules.auth.roles import ROLE_CAPABILITIES
from app.modules.auth.security import hash_password

SYNTHETIC_LABEL = "SYNTHETIC / DEVELOPMENT DATA"
DEVELOPMENT_ORGANIZATION = f"{SYNTHETIC_LABEL} National Authority"
ROLE_EMAILS = {
    "Platform Super Admin": "super-admin@development.invalid",
    "National Analyst": "national-analyst@development.invalid",
    "Regional Analyst": "regional-analyst@development.invalid",
    "District Officer / Field Reporter": "district-officer@development.invalid",
    "Early Action / Response Coordinator": "response-coordinator@development.invalid",
    "Decision Maker": "decision-maker@development.invalid",
    "Data / ML Scientist": "ml-scientist@development.invalid",
    "Partner / Read-only Viewer": "partner-viewer@development.invalid",
}


@dataclass(frozen=True)
class SeedResult:
    created_users: int
    accounts: tuple[str, ...]
    synthetic_alert_id: UUID


def seed_development(db: Session, settings: Settings, password: str) -> SeedResult:
    if settings.environment.lower() not in {"development", "test"}:
        raise RuntimeError("Development seeding is disabled outside development/test")
    if len(password) < 12:
        raise ValueError("SEED_PASSWORD must contain at least 12 characters")

    organization = db.scalar(
        select(Organization).where(Organization.name == DEVELOPMENT_ORGANIZATION)
    )
    if organization is None:
        organization = Organization(
            name=DEVELOPMENT_ORGANIZATION,
            organization_type="synthetic national institution",
        )
        db.add(organization)
        db.flush()

    country = _admin_unit(db, "SO-SYN", "Synthetic Somalia", "country", None)
    region = _admin_unit(db, "SO-SYN-R1", "Synthetic Region", "region", country.id)
    district = _admin_unit(db, "SO-SYN-D1", "Synthetic District", "district", region.id)

    created_users = 0
    users: dict[str, User] = {}
    for role_name, capabilities in ROLE_CAPABILITIES.items():
        role = db.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            role = Role(
                name=role_name,
                description=f"Development role: {role_name}",
                capabilities=sorted(capabilities),
            )
            db.add(role)
            db.flush()
        else:
            role.capabilities = sorted(capabilities)
        email = ROLE_EMAILS[role_name]
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                display_name=f"Synthetic {role_name}",
                password_hash=hash_password(password),
            )
            db.add(user)
            db.flush()
            created_users += 1
        users[role_name] = user
        membership = db.scalar(
            select(Membership).where(
                Membership.user_id == user.id,
                Membership.organization_id == organization.id,
                Membership.role_id == role.id,
            )
        )
        if membership is None:
            membership = Membership(
                user_id=user.id,
                organization_id=organization.id,
                role_id=role.id,
                classification_ceiling=(
                    Classification.PARTNER
                    if role_name == "Partner / Read-only Viewer"
                    else Classification.INTERNAL
                ),
            )
            db.add(membership)
            db.flush()
            db.add(GeographicScope(membership_id=membership.id, national=True))

    source = db.scalar(select(DataSource).where(DataSource.name == f"{SYNTHETIC_LABEL} Source"))
    if source is None:
        source = DataSource(
            name=f"{SYNTHETIC_LABEL} Source",
            domain="drought",
            license="Synthetic fixture license",
            attribution=SYNTHETIC_LABEL,
            owner="Local development seed",
            terms_url="https://example.invalid/synthetic-fixture-terms",
            expected_frequency_minutes=1440,
            geographic_resolution="synthetic district",
            historical_start=date(2020, 1, 1),
            schedule="development only",
            access_method="file",
            classification=Classification.INTERNAL,
            verified=True,
        )
        db.add(source)
        db.flush()
    observation = db.scalar(
        select(Observation).where(
            Observation.source_id == source.id,
            Observation.source_record_id == "synthetic-seed-drought-1",
        )
    )
    if observation is None:
        observation = Observation(
            source_id=source.id,
            source_record_id="synthetic-seed-drought-1",
            admin_unit_id=district.id,
            indicator_code="drought.rainfall_deficit",
            value=0.7,
            value_kind="observed",
            unit="index_0_1",
            reference_time=datetime(2027, 1, 1, tzinfo=timezone.utc),
            retrieved_at=datetime(2027, 1, 2, tzinfo=timezone.utc),
            stage=DataStage.NORMALIZED,
            quality_flags=["synthetic_development_data"],
            boundary_version=district.boundary_version,
        )
        db.add(observation)
    signal = db.scalar(
        select(RiskSignal).where(
            RiskSignal.admin_unit_id == district.id,
            RiskSignal.domain == RiskDomain.DROUGHT,
            RiskSignal.target_period == "SYNTHETIC-2027-Gu",
        )
    )
    if signal is None:
        signal = RiskSignal(
            domain=RiskDomain.DROUGHT,
            admin_unit_id=district.id,
            level=RiskLevel.WARNING,
            score=0.7,
            confidence=0.6,
            drivers=[{"source_id": str(source.id), "indicator": observation.indicator_code}],
            provenance={"label": SYNTHETIC_LABEL, "automatic_warning_publication": False},
            target_period="SYNTHETIC-2027-Gu",
        )
        db.add(signal)
        db.flush()
    alert = db.scalar(select(Alert).where(Alert.title == f"{SYNTHETIC_LABEL} Drought Warning"))
    analyst = users["National Analyst"]
    if alert is None:
        alert = Alert(
            signal_id=signal.id,
            status=AlertStatus.PUBLISHED,
            classification=Classification.PUBLIC,
            title=f"{SYNTHETIC_LABEL} Drought Warning",
            summary="Synthetic warning for local workflow demonstration only.",
            approved_by=analyst.id,
            published_at=datetime.now(timezone.utc),
        )
        db.add(alert)
        db.flush()
    playbook = db.scalar(select(Playbook).where(Playbook.name == f"{SYNTHETIC_LABEL} Playbook"))
    if playbook is None:
        playbook = Playbook(
            name=f"{SYNTHETIC_LABEL} Playbook",
            risk_domain=RiskDomain.DROUGHT,
            approved=True,
            approved_by=analyst.id,
            version="development-v1",
            steps=[{"action": "Verify synthetic water access"}],
        )
        db.add(playbook)
        db.flush()
    plan = db.scalar(
        select(ActionPlan).where(
            ActionPlan.alert_id == alert.id,
            ActionPlan.title == f"{SYNTHETIC_LABEL} Response Plan",
        )
    )
    if plan is None:
        plan = ActionPlan(
            alert_id=alert.id,
            playbook_id=playbook.id,
            owner_organization_id=organization.id,
            title=f"{SYNTHETIC_LABEL} Response Plan",
            approved=True,
        )
        db.add(plan)
        db.flush()
    if not db.scalar(select(ActionItem.id).where(ActionItem.plan_id == plan.id)):
        db.add(
            ActionItem(
                plan_id=plan.id,
                owner_organization_id=organization.id,
                description="Inspect synthetic water points",
                due_at=datetime(2027, 2, 1, tzinfo=timezone.utc),
                status=ActionStatus.PLANNED,
                blockers=[],
                evidence_objects=[],
            )
        )
    db.commit()
    return SeedResult(created_users, tuple(ROLE_EMAILS.values()), alert.id)


def _admin_unit(
    db: Session, stable_code: str, name: str, level: str, parent_id: UUID | None
) -> AdminUnit:
    unit = db.scalar(select(AdminUnit).where(AdminUnit.stable_code == stable_code))
    if unit is None:
        unit = AdminUnit(
            stable_code=stable_code,
            name=name,
            level=level,
            parent_id=parent_id,
            boundary_version="synthetic-development-v1",
            boundary_source=SYNTHETIC_LABEL,
            valid_from=date(2020, 1, 1),
            aliases=[],
        )
        db.add(unit)
        db.flush()
    return unit
