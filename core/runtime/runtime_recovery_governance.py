from dataclasses import dataclass
from core.runtime.runtime_recovery_risk import (
    RuntimeRecoveryRisk,
    RISK_LOW,
    RISK_MEDIUM,
    RISK_HIGH,
)
from core.runtime.runtime_recovery_approval import RuntimeRecoveryApproval

STATUS_ALLOWED = "allowed"
STATUS_BLOCKED = "blocked"
STATUS_REVIEW_REQUIRED = "review_required"

@dataclass(frozen=True)
class RuntimeRecoveryGovernanceResult:
    status: str
    risk: str
    approval_required: bool

def classify_recovery_risk(payload: dict) -> RuntimeRecoveryRisk:
    rollback_required = bool(payload.get("rollback_required"))
    mutation_scope = str(payload.get("mutation_scope") or "safe")

    if rollback_required:
        return RuntimeRecoveryRisk(RISK_HIGH, "rollback_required")

    if mutation_scope == "extended":
        return RuntimeRecoveryRisk(RISK_MEDIUM, "extended_mutation_scope")

    return RuntimeRecoveryRisk(RISK_LOW, "safe")

def evaluate_recovery_governance(payload: dict) -> RuntimeRecoveryGovernanceResult:
    risk = classify_recovery_risk(payload)

    if risk.classification == RISK_HIGH:
        approval = RuntimeRecoveryApproval(True, False)
        return RuntimeRecoveryGovernanceResult(
            status=STATUS_BLOCKED,
            risk=risk.classification,
            approval_required=approval.approval_required,
        )

    if risk.classification == RISK_MEDIUM:
        approval = RuntimeRecoveryApproval(True, False)
        return RuntimeRecoveryGovernanceResult(
            status=STATUS_REVIEW_REQUIRED,
            risk=risk.classification,
            approval_required=approval.approval_required,
        )

    return RuntimeRecoveryGovernanceResult(
        status=STATUS_ALLOWED,
        risk=risk.classification,
        approval_required=False,
    )
