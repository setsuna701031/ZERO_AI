from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_execution_authority_evidence import (
    build_execution_authority_evidence,
    export_execution_authority_evidence,
)
from core.runtime.runtime_execution_authority_policy import (
    RuntimeExecutionAuthorityDecision,
    RuntimeExecutionAuthorityPolicy,
)


class RuntimeExecutionAuthorityDenied(PermissionError):
    def __init__(
        self,
        decision: RuntimeExecutionAuthorityDecision,
        evidence: dict[str, Any],
    ) -> None:
        self.decision = decision
        self.evidence = evidence
        super().__init__(decision.reason)


class RuntimeExecutionAuthorityGate:
    """Enforce canonical execution authority without executing work."""

    def __init__(
        self,
        policy: RuntimeExecutionAuthorityPolicy | None = None,
    ) -> None:
        self.policy = policy or RuntimeExecutionAuthorityPolicy()

    def evaluate(
        self,
        *,
        source: Any,
        action_type: Any,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeExecutionAuthorityDecision:
        return self.policy.evaluate(
            source=source,
            action_type=action_type,
            metadata=metadata,
        )

    def enforce(
        self,
        *,
        source: Any,
        action_type: Any,
        metadata: Mapping[str, Any] | None = None,
        repo_root: Path | str | None = None,
        task_id: str = "runtime_execution_authority",
    ) -> RuntimeExecutionAuthorityDecision:
        decision = self.evaluate(
            source=source,
            action_type=action_type,
            metadata=metadata,
        )
        if decision.allowed:
            return decision

        evidence = build_execution_authority_evidence(decision, metadata=metadata)
        if repo_root is not None:
            evidence = export_execution_authority_evidence(
                repo_root=repo_root,
                task_id=task_id,
                decision=decision,
                metadata=metadata,
            )["payload"]
        raise RuntimeExecutionAuthorityDenied(decision, evidence)


def enforce_execution_authority(
    *,
    source: Any,
    action_type: Any,
    metadata: Mapping[str, Any] | None = None,
    repo_root: Path | str | None = None,
    task_id: str = "runtime_execution_authority",
) -> RuntimeExecutionAuthorityDecision:
    return RuntimeExecutionAuthorityGate().enforce(
        source=source,
        action_type=action_type,
        metadata=metadata,
        repo_root=repo_root,
        task_id=task_id,
    )


__all__ = [
    "RuntimeExecutionAuthorityDenied",
    "RuntimeExecutionAuthorityGate",
    "enforce_execution_authority",
]
