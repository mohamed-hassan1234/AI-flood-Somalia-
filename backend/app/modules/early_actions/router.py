from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import ActionStatus, AlertStatus
from app.db.models.core import (
    ActionItem,
    ActionPlan,
    Alert,
    AuditEvent,
    Organization,
    Playbook,
    RiskSignal,
    User,
)
from app.db.session import get_db
from app.modules.auth.dependencies import (
    Principal,
    get_current_principal,
    has_access,
    require_access,
)
from app.modules.early_actions.schemas import (
    ActionItemCreate,
    ActionItemListResponse,
    ActionItemResponse,
    ActionItemTransition,
    ActionPlanCreate,
    ActionPlanResponse,
    PlaybookCreate,
    PlaybookResponse,
)
from app.modules.early_actions.service import transition

router = APIRouter(prefix="/early-actions", tags=["early actions"])


@router.get("/items", response_model=list[ActionItemListResponse])
def list_items(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ActionItemListResponse]:
    rows = db.execute(
        select(ActionItem, ActionPlan, Alert, RiskSignal)
        .join(ActionPlan, ActionPlan.id == ActionItem.plan_id)
        .join(Alert, Alert.id == ActionPlan.alert_id)
        .join(RiskSignal, RiskSignal.id == Alert.signal_id)
        .order_by(ActionItem.due_at, ActionItem.created_at)
    ).all()
    return [
        ActionItemListResponse(
            id=item.id,
            plan_id=plan.id,
            plan_title=plan.title,
            alert_title=alert.title,
            risk_domain=signal.domain,
            classification=alert.classification.value,
            admin_unit_id=signal.admin_unit_id,
            owner_id=item.owner_id,
            owner_organization_id=item.owner_organization_id,
            description=item.description,
            due_at=item.due_at,
            status=item.status,
            blockers=item.blockers,
            evidence_count=len(item.evidence_objects),
        )
        for item, plan, alert, signal in rows
        if has_access(
            principal, "early_actions.read", alert.classification, signal.admin_unit_id
        )
    ]


def _plan_context(db: Session, plan_id: UUID) -> tuple[ActionPlan, Alert, RiskSignal]:
    plan = db.get(ActionPlan, plan_id)
    alert = db.get(Alert, plan.alert_id) if plan else None
    signal = db.get(RiskSignal, alert.signal_id) if alert else None
    if plan is None or alert is None or signal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Action plan not found")
    return plan, alert, signal


def _audit(
    db: Session,
    principal: Principal,
    action: str,
    entity_type: str,
    entity_id: UUID,
    details: dict[str, object],
) -> None:
    db.add(
        AuditEvent(
            id=uuid4(),
            occurred_at=datetime.now(timezone.utc),
            actor_id=principal.user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
        )
    )


@router.post("/playbooks", response_model=PlaybookResponse, status_code=status.HTTP_201_CREATED)
def create_playbook(
    body: PlaybookCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Playbook:
    if "early_actions.playbooks.manage" not in principal.capabilities:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Missing capability: early_actions.playbooks.manage"
        )
    playbook = Playbook(**body.model_dump(), approved=False)
    db.add(playbook)
    db.commit()
    db.refresh(playbook)
    return playbook


@router.post("/playbooks/{playbook_id}/approval", response_model=PlaybookResponse)
def approve_playbook(
    playbook_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> Playbook:
    if "early_actions.approve" not in principal.capabilities:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing capability: early_actions.approve")
    playbook = db.get(Playbook, playbook_id)
    if playbook is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playbook not found")
    playbook.approved = True
    playbook.approved_by = principal.user_id
    db.commit()
    db.refresh(playbook)
    return playbook


@router.post("/plans", response_model=ActionPlanResponse, status_code=status.HTTP_201_CREATED)
def create_plan(
    body: ActionPlanCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> ActionPlan:
    alert = db.get(Alert, body.alert_id)
    signal = db.get(RiskSignal, alert.signal_id) if alert else None
    playbook = db.get(Playbook, body.playbook_id)
    if alert is None or signal is None or playbook is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert or playbook not found")
    require_access(principal, "early_actions.create", alert.classification, signal.admin_unit_id)
    if alert.status is not AlertStatus.PUBLISHED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Action plan requires a published warning")
    if not playbook.approved or playbook.risk_domain is not signal.domain:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Approved playbook must match the warning domain"
        )
    if db.get(Organization, body.owner_organization_id) is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Owner organization does not exist"
        )
    plan = ActionPlan(**body.model_dump(), approved=False)
    db.add(plan)
    db.flush()
    _audit(db, principal, "early_actions.create", "action_plan", plan.id, {})
    db.commit()
    db.refresh(plan)
    return plan


@router.post("/plans/{plan_id}/approval", response_model=ActionPlanResponse)
def approve_plan(
    plan_id: UUID,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> ActionPlan:
    plan, alert, signal = _plan_context(db, plan_id)
    require_access(principal, "early_actions.approve", alert.classification, signal.admin_unit_id)
    plan.approved = True
    _audit(db, principal, "early_actions.approve", "action_plan", plan.id, {})
    db.commit()
    db.refresh(plan)
    return plan


@router.post(
    "/plans/{plan_id}/items", response_model=ActionItemResponse, status_code=status.HTTP_201_CREATED
)
def create_item(
    plan_id: UUID,
    body: ActionItemCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> ActionItem:
    plan, alert, signal = _plan_context(db, plan_id)
    require_access(principal, "early_actions.assign", alert.classification, signal.admin_unit_id)
    if not plan.approved:
        raise HTTPException(status.HTTP_409_CONFLICT, "Action plan is not approved")
    if db.get(Organization, body.owner_organization_id) is None or (
        body.owner_id and db.get(User, body.owner_id) is None
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Action owner does not exist")
    item = ActionItem(
        plan_id=plan.id,
        status=ActionStatus.PLANNED,
        blockers=[],
        evidence_objects=[],
        **body.model_dump(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/items/{item_id}/transitions", response_model=ActionItemResponse)
def transition_item(
    item_id: UUID,
    body: ActionItemTransition,
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_db)],
) -> ActionItem:
    item = db.get(ActionItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Action item not found")
    _, alert, signal = _plan_context(db, item.plan_id)
    capability = (
        "early_actions.complete"
        if body.target is ActionStatus.COMPLETED
        else "early_actions.update"
    )
    require_access(principal, capability, alert.classification, signal.admin_unit_id)
    try:
        item.status = transition(item.status, body.target, {capability}, len(body.evidence_objects))
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    item.blockers = body.blockers
    item.evidence_objects = body.evidence_objects
    _audit(db, principal, capability, "action_item", item.id, {"status": item.status.value})
    db.commit()
    db.refresh(item)
    return item
