from enum import Enum


class Classification(str, Enum):
    INTERNAL = "internal"
    PARTNER = "partner"
    PUBLIC = "public"


class RiskLevel(str, Enum):
    NORMAL = "normal"
    WATCH = "watch"
    WARNING = "warning"
    CRITICAL = "critical"


class RiskDomain(str, Enum):
    DROUGHT = "drought"
    RIVER_FLOOD = "river_flood"
    FLASH_FLOOD = "flash_flood"
    FOOD_SECURITY = "food_security_deterioration"


class AlertStatus(str, Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    VERIFICATION_REQUIRED = "verification_required"
    VERIFIED = "verified"
    APPROVED = "approved"
    PUBLISHED = "published"
    RESOLVED = "resolved"


class DataStage(str, Enum):
    RAW = "raw"
    VALIDATED = "validated"
    NORMALIZED = "normalized"
    DERIVED = "derived"
    PUBLISHED = "published"


class VerificationStatus(str, Enum):
    OPEN = "open"
    SUBMITTED = "submitted"
    VERIFIED = "verified"
    REJECTED = "rejected"
    MORE_EVIDENCE = "more_evidence_required"


class ActionStatus(str, Enum):
    PLANNED = "planned"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DeliveryStatus(str, Enum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    ACKNOWLEDGED = "acknowledged"


class ReportStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
