from dataclasses import dataclass

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"

@dataclass(frozen=True)
class RuntimeRecoveryRisk:
    classification: str
    reason: str = ""
