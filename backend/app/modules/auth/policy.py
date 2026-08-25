from dataclasses import dataclass
from uuid import UUID

from app.core.enums import Classification

_CLASSIFICATION_RANK = {
    Classification.PUBLIC: 0,
    Classification.PARTNER: 1,
    Classification.INTERNAL: 2,
}


@dataclass(frozen=True)
class AccessContext:
    user_id: UUID
    capabilities: frozenset[str]
    classification_ceiling: Classification
    national: bool = False
    admin_unit_ids: frozenset[UUID] = frozenset()


def authorize(
    context: AccessContext,
    capability: str,
    classification: Classification,
    admin_unit_id: UUID | None,
) -> None:
    if capability not in context.capabilities:
        raise PermissionError(f"Missing capability: {capability}")
    if _CLASSIFICATION_RANK[classification] > _CLASSIFICATION_RANK[context.classification_ceiling]:
        raise PermissionError("Information classification exceeds access ceiling")
    if (
        admin_unit_id is not None
        and not context.national
        and admin_unit_id not in context.admin_unit_ids
    ):
        raise PermissionError("Geographic scope does not include this administrative unit")
