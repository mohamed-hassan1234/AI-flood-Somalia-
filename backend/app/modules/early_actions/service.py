from app.core.enums import ActionStatus

TRANSITIONS = {
    ActionStatus.PLANNED: {ActionStatus.ASSIGNED, ActionStatus.CANCELLED},
    ActionStatus.ASSIGNED: {ActionStatus.IN_PROGRESS, ActionStatus.BLOCKED, ActionStatus.CANCELLED},
    ActionStatus.IN_PROGRESS: {ActionStatus.BLOCKED, ActionStatus.COMPLETED},
    ActionStatus.BLOCKED: {ActionStatus.IN_PROGRESS, ActionStatus.CANCELLED},
    ActionStatus.COMPLETED: set(),
    ActionStatus.CANCELLED: set(),
}


def transition(
    current: ActionStatus, target: ActionStatus, capabilities: set[str], evidence_count: int = 0
) -> ActionStatus:
    if target not in TRANSITIONS[current]:
        raise ValueError("Invalid early-action transition")
    required = (
        "early_actions.complete" if target is ActionStatus.COMPLETED else "early_actions.update"
    )
    if required not in capabilities:
        raise PermissionError(f"Missing capability: {required}")
    if target is ActionStatus.COMPLETED and evidence_count < 1:
        raise ValueError("Completion requires evidence")
    return target
