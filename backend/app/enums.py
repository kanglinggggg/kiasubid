from enum import StrEnum


class OperationalStatus(StrEnum):
    FEASIBLE = "FEASIBLE"
    RECOVERABLE = "RECOVERABLE"
    BLOCKED = "BLOCKED"
    UNCERTAIN = "UNCERTAIN"


class AssessmentStatus(StrEnum):
    SATISFIED = "SATISFIED"
    PARTIAL = "PARTIAL"
    UNMET = "UNMET"
    UNCERTAIN = "UNCERTAIN"
    SUPERSEDED = "SUPERSEDED"


class GateType(StrEnum):
    MANDATORY = "MANDATORY"
    SCORED = "SCORED"
    INFORMATIONAL = "INFORMATIONAL"


class VerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    STALE = "STALE"
    MISSING = "MISSING"
    UNVERIFIED = "UNVERIFIED"


class AvailabilityStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class TaskStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING = "WAITING"
    DONE = "DONE"
    BLOCKED = "BLOCKED"


class TaskPriority(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class DeadlineRisk(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    MISSED = "MISSED"
