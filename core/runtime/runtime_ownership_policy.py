from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping


CANONICAL_EXECUTION_PATH = (
    "runtime.execution_gateway",
    "runtime.executor",
)

ORCHESTRATION_ONLY_SURFACES = {
    "agent_loop",
    "scheduler",
    "system_boot",
}

FORBIDDEN_EXECUTION_CALLS = {
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "os.system",
    "run_mutation_runtime_pipeline",
    "run_governed_mutation_runtime",
    "run_recovery",
    "execute_recovery",
    "safe_subprocess_run",
}

FORBIDDEN_WRITE_CALLS = {
    "write_text",
    "write_bytes",
    "open",
}

ALLOWED_GATEWAY_MODULES = {
    "core/runtime/execution_gateway.py",
    "core/runtime/executor.py",
}


@dataclass(frozen=True)
class RuntimeOwnershipPolicyViolation:
    file_path: str
    line: int
    owner: str
    violation_type: str
    symbol: str
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "line": self.line,
            "owner": self.owner,
            "violation_type": self.violation_type,
            "symbol": self.symbol,
            "reason": self.reason,
            "evidence": copy.deepcopy(self.evidence),
        }


def evaluate_ownership_findings(
    findings: list[Mapping[str, Any]],
    *,
    owner: str = "",
) -> dict[str, Any]:
    violations = [
        _violation_from_finding(finding, owner=owner)
        for finding in findings
        if _finding_is_violation(finding)
    ]
    payload = {
        "schema": "runtime_ownership_policy_report.v1",
        "ok": not violations,
        "canonical_execution_path": list(CANONICAL_EXECUTION_PATH),
        "owner": str(owner or ""),
        "violation_count": len(violations),
        "violations": [violation.to_dict() for violation in violations],
        "no_execution_added": True,
        "policy_only": True,
    }
    return payload


def _finding_is_violation(finding: Mapping[str, Any]) -> bool:
    return bool(finding.get("violation"))


def _violation_from_finding(
    finding: Mapping[str, Any],
    *,
    owner: str = "",
) -> RuntimeOwnershipPolicyViolation:
    return RuntimeOwnershipPolicyViolation(
        file_path=str(finding.get("file_path") or ""),
        line=int(finding.get("line") or 0),
        owner=str(finding.get("owner") or owner or ""),
        violation_type=str(finding.get("violation_type") or "ownership_violation"),
        symbol=str(finding.get("symbol") or ""),
        reason=str(finding.get("reason") or "runtime ownership violation"),
        evidence=copy.deepcopy(dict(finding.get("evidence") or {})),
    )


__all__ = [
    "ALLOWED_GATEWAY_MODULES",
    "CANONICAL_EXECUTION_PATH",
    "FORBIDDEN_EXECUTION_CALLS",
    "FORBIDDEN_WRITE_CALLS",
    "ORCHESTRATION_ONLY_SURFACES",
    "RuntimeOwnershipPolicyViolation",
    "evaluate_ownership_findings",
]
