"""Immutable runtime execution policy decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from core.runtime.runtime_execution_request import RuntimeExecutionRequest


__all__ = [
    "EXECUTION_POLICY_STATES",
    "EXECUTION_RISK_LEVELS",
    "ExecutionPolicyDecision",
    "ExecutionPolicyResult",
    "RuntimeExecutionPolicy",
    "classify_execution_risk",
]


EXECUTION_POLICY_STATES = frozenset(
    {
        "allowed",
        "blocked",
        "requires_confirmation",
        "dry_run_only",
        "sandbox_required",
        "rollback_required",
    }
)

EXECUTION_RISK_LEVELS = frozenset(
    {
        "LOW",
        "MODERATE",
        "HIGH",
        "IRREVERSIBLE",
        "EXTERNAL",
    }
)


@dataclass(frozen=True)
class ExecutionPolicyDecision:
    state: str
    reason: str
    risk_level: str
    policy_source: str
    lineage: dict[str, Any] = field(default_factory=dict)
    audit_tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.state in {
            "allowed",
            "dry_run_only",
            "sandbox_required",
            "rollback_required",
        }


@dataclass(frozen=True)
class ExecutionPolicyResult:
    decision: ExecutionPolicyDecision
    request: RuntimeExecutionRequest
    evaluated: bool = True

    @property
    def allowed(self) -> bool:
        return self.decision.allowed

    @property
    def state(self) -> str:
        return self.decision.state

    @property
    def risk_level(self) -> str:
        return self.decision.risk_level

    def to_metadata(self) -> dict[str, Any]:
        return {
            "policy_evaluated": self.evaluated,
            "policy_state": self.decision.state,
            "policy_reason": self.decision.reason,
            "policy_source": self.decision.policy_source,
            "risk_level": self.decision.risk_level,
            "policy_audit_tags": list(self.decision.audit_tags),
            "policy_lineage": dict(self.decision.lineage),
            "policy_metadata": dict(self.decision.metadata),
        }


class RuntimeExecutionPolicy:
    """Policy evaluator for canonical runtime execution requests."""

    policy_source = "core.runtime.runtime_execution_policy"

    def evaluate(self, request: RuntimeExecutionRequest) -> ExecutionPolicyResult:
        if not isinstance(request, RuntimeExecutionRequest):
            raise TypeError("RuntimeExecutionRequest is required")

        risk_level = classify_execution_risk(
            execution_type=request.execution_type,
            command=request.command,
            metadata=request.metadata,
        )
        lineage = dict(request.lineage)
        audit_tags = self._audit_tags_for_request(request, risk_level)

        if not self._has_authority_metadata(request.metadata):
            return self._result(
                request=request,
                state="blocked",
                reason="runtime_authority_metadata_required",
                risk_level=risk_level,
                lineage=lineage,
                audit_tags=(*audit_tags, "authority_missing"),
            )

        if "provenance" not in request.metadata:
            return self._result(
                request=request,
                state="blocked",
                reason="runtime_provenance_metadata_required",
                risk_level=risk_level,
                lineage=lineage,
                audit_tags=(*audit_tags, "provenance_missing"),
            )

        if request.dry_run:
            return self._result(
                request=request,
                state="dry_run_only",
                reason="request_marked_dry_run",
                risk_level=risk_level,
                lineage=lineage,
                audit_tags=(*audit_tags, "dry_run"),
            )

        if not str(request.execution_type or "").strip():
            return self._result(
                request=request,
                state="blocked",
                reason="execution_type_required",
                risk_level=risk_level,
                lineage=lineage,
                audit_tags=audit_tags,
            )

        if request.execution_type not in {"command", "subprocess", "mutation"}:
            return self._result(
                request=request,
                state="blocked",
                reason=f"unsupported_execution_type:{request.execution_type}",
                risk_level=risk_level,
                lineage=lineage,
                audit_tags=audit_tags,
            )

        if bool(request.metadata.get("requires_confirmation", False)):
            return self._result(
                request=request,
                state="requires_confirmation",
                reason="confirmation_required_by_metadata",
                risk_level=risk_level,
                lineage=lineage,
                audit_tags=(*audit_tags, "confirmation"),
            )

        if bool(request.metadata.get("sandbox_required", False)):
            return self._result(
                request=request,
                state="sandbox_required",
                reason="sandbox_required_by_metadata",
                risk_level=risk_level,
                lineage=lineage,
                audit_tags=(*audit_tags, "sandbox"),
            )

        if bool(request.metadata.get("rollback_required", False)):
            return self._result(
                request=request,
                state="rollback_required",
                reason="rollback_required_by_metadata",
                risk_level=risk_level,
                lineage=lineage,
                audit_tags=(*audit_tags, "rollback"),
            )

        return self._result(
            request=request,
            state="allowed",
            reason="runtime_execution_request_accepted",
            risk_level=risk_level,
            lineage=lineage,
            audit_tags=audit_tags,
        )

    def _result(
        self,
        *,
        request: RuntimeExecutionRequest,
        state: str,
        reason: str,
        risk_level: str,
        lineage: Mapping[str, Any],
        audit_tags: tuple[str, ...],
    ) -> ExecutionPolicyResult:
        if state not in EXECUTION_POLICY_STATES:
            state = "blocked"
            reason = "invalid_policy_state"
        if risk_level not in EXECUTION_RISK_LEVELS:
            risk_level = "HIGH"
        decision = ExecutionPolicyDecision(
            state=state,
            reason=reason,
            risk_level=risk_level,
            policy_source=self.policy_source,
            lineage=dict(lineage),
            audit_tags=tuple(audit_tags),
            metadata={
                "execution_type": request.execution_type,
                "dry_run": request.dry_run,
                "shell": bool(request.metadata.get("shell", False)),
            },
        )
        return ExecutionPolicyResult(decision=decision, request=request)

    def _audit_tags_for_request(
        self,
        request: RuntimeExecutionRequest,
        risk_level: str,
    ) -> tuple[str, ...]:
        tags = ["execution", f"risk:{risk_level}"]
        execution_type = str(request.execution_type or "").strip()
        if execution_type:
            tags.append(f"type:{execution_type}")
        if bool(request.metadata.get("shell", False)):
            tags.append("shell")
        if request.replay_id:
            tags.append("replay_tagged")
        if request.repair_session_id:
            tags.append("repair_tagged")
        return tuple(tags)

    def _has_authority_metadata(self, metadata: Mapping[str, Any]) -> bool:
        identity = metadata.get("runtime_identity")
        return isinstance(identity, Mapping) and bool(identity.get("identity_id"))


def classify_execution_risk(
    *,
    execution_type: str,
    command: Any = None,
    metadata: Mapping[str, Any] | None = None,
) -> str:
    metadata = dict(metadata or {})
    operation = str(
        metadata.get("operation")
        or metadata.get("effect_type")
        or execution_type
        or ""
    ).strip().lower()
    command_text = _command_text(command).lower()

    if metadata.get("network") or operation in {"network", "network_action"}:
        return "EXTERNAL"
    if operation in {"external_process", "external"}:
        return "EXTERNAL"
    if operation in {"subprocess", "command", "command_execution"}:
        if bool(metadata.get("shell", False)):
            return "HIGH"
        return "MODERATE"
    if operation in {"git", "git_operation"} or command_text.startswith("git "):
        if any(token in command_text for token in (" push", " reset", " clean", " revert")):
            return "IRREVERSIBLE"
        return "MODERATE"
    if operation in {"apply_patch", "patch_apply", "apply_unified_diff"}:
        return "HIGH"
    if operation in {"file_mutation", "write_file", "append_file", "mkdir"}:
        return "MODERATE"
    if any(token in command_text for token in ("curl ", "wget ", "ssh ", "scp ")):
        return "EXTERNAL"
    if any(token in command_text for token in (" rm ", "del ", "format ", "reset --hard")):
        return "IRREVERSIBLE"
    return "LOW"


def _command_text(command: Any) -> str:
    if isinstance(command, (list, tuple)):
        return " ".join(str(item) for item in command)
    return str(command or "")
