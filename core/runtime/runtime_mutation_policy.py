"""Immutable runtime mutation policy contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


MUTATION_POLICY_STATES = frozenset(
    {
        "allowed",
        "blocked",
        "requires_confirmation",
        "dry_run_only",
        "sandbox_required",
        "rollback_required",
        "snapshot_required",
    }
)

MUTATION_RISK_LEVELS = frozenset(
    {
        "LOW",
        "MODERATE",
        "HIGH",
        "IRREVERSIBLE",
        "EXTERNAL",
    }
)


@dataclass(frozen=True)
class MutationPolicyDecision:
    state: str
    reason: str
    risk_level: str
    policy_source: str
    target_path: str | None
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
            "snapshot_required",
        }


@dataclass(frozen=True)
class MutationPolicyResult:
    decision: MutationPolicyDecision
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
            "mutation_policy_evaluated": self.evaluated,
            "mutation_policy_state": self.decision.state,
            "mutation_policy_reason": self.decision.reason,
            "mutation_policy_source": self.decision.policy_source,
            "risk_level": self.decision.risk_level,
            "target_path": self.decision.target_path,
            "mutation_policy_lineage": dict(self.decision.lineage),
            "mutation_policy_audit_tags": list(self.decision.audit_tags),
            "mutation_policy_metadata": dict(self.decision.metadata),
        }


class RuntimeMutationPolicy:
    policy_source = "core.runtime.runtime_mutation_policy"

    def evaluate(
        self,
        *,
        operation_type: str,
        target_path: str | Path | None,
        lineage: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> MutationPolicyResult:
        metadata = dict(metadata or {})
        lineage_dict = dict(lineage or {})
        operation = str(operation_type or "").strip().lower()
        target_text = str(target_path) if target_path is not None else None
        risk_level = classify_mutation_risk(
            operation_type=operation,
            target_path=target_text,
            metadata=metadata,
        )
        audit_tags = self._audit_tags(operation, risk_level, metadata)

        if not operation:
            return self._result(
                state="blocked",
                reason="operation_type_required",
                risk_level=risk_level,
                target_path=target_text,
                lineage=lineage_dict,
                audit_tags=audit_tags,
                metadata=metadata,
            )

        if operation not in {
            "file_write",
            "file_delete",
            "patch_apply",
            "generated_artifact_write",
            "config_mutation",
            "source_code_mutation",
            "git_mutation",
            "external_state_mutation",
        }:
            return self._result(
                state="blocked",
                reason=f"unsupported_mutation_type:{operation}",
                risk_level=risk_level,
                target_path=target_text,
                lineage=lineage_dict,
                audit_tags=audit_tags,
                metadata=metadata,
            )

        if metadata.get("dry_run"):
            return self._result(
                state="dry_run_only",
                reason="mutation_marked_dry_run",
                risk_level=risk_level,
                target_path=target_text,
                lineage=lineage_dict,
                audit_tags=(*audit_tags, "dry_run"),
                metadata=metadata,
            )

        if metadata.get("blocked"):
            return self._result(
                state="blocked",
                reason="mutation_blocked_by_metadata",
                risk_level=risk_level,
                target_path=target_text,
                lineage=lineage_dict,
                audit_tags=(*audit_tags, "blocked"),
                metadata=metadata,
            )

        if metadata.get("requires_confirmation"):
            return self._result(
                state="requires_confirmation",
                reason="mutation_requires_confirmation",
                risk_level=risk_level,
                target_path=target_text,
                lineage=lineage_dict,
                audit_tags=(*audit_tags, "confirmation"),
                metadata=metadata,
            )

        if metadata.get("sandbox_required"):
            return self._result(
                state="sandbox_required",
                reason="mutation_requires_sandbox",
                risk_level=risk_level,
                target_path=target_text,
                lineage=lineage_dict,
                audit_tags=(*audit_tags, "sandbox"),
                metadata=metadata,
            )

        if metadata.get("rollback_required") or operation in {
            "file_delete",
            "patch_apply",
            "source_code_mutation",
            "git_mutation",
        }:
            return self._result(
                state="rollback_required",
                reason="mutation_requires_rollback_trace",
                risk_level=risk_level,
                target_path=target_text,
                lineage=lineage_dict,
                audit_tags=(*audit_tags, "rollback"),
                metadata=metadata,
            )

        if metadata.get("snapshot_required", True):
            return self._result(
                state="snapshot_required",
                reason="mutation_requires_pre_snapshot",
                risk_level=risk_level,
                target_path=target_text,
                lineage=lineage_dict,
                audit_tags=(*audit_tags, "snapshot"),
                metadata=metadata,
            )

        return self._result(
            state="allowed",
            reason="mutation_allowed",
            risk_level=risk_level,
            target_path=target_text,
            lineage=lineage_dict,
            audit_tags=audit_tags,
            metadata=metadata,
        )

    def _result(
        self,
        *,
        state: str,
        reason: str,
        risk_level: str,
        target_path: str | None,
        lineage: Mapping[str, Any],
        audit_tags: tuple[str, ...],
        metadata: Mapping[str, Any],
    ) -> MutationPolicyResult:
        if state not in MUTATION_POLICY_STATES:
            state = "blocked"
            reason = "invalid_mutation_policy_state"
        if risk_level not in MUTATION_RISK_LEVELS:
            risk_level = "HIGH"
        return MutationPolicyResult(
            decision=MutationPolicyDecision(
                state=state,
                reason=reason,
                risk_level=risk_level,
                policy_source=self.policy_source,
                target_path=target_path,
                lineage=dict(lineage),
                audit_tags=tuple(audit_tags),
                metadata=dict(metadata),
            )
        )

    def _audit_tags(
        self,
        operation_type: str,
        risk_level: str,
        metadata: Mapping[str, Any],
    ) -> tuple[str, ...]:
        tags = ["mutation", f"operation:{operation_type}", f"risk:{risk_level}"]
        if metadata.get("replay_id"):
            tags.append("replay_tagged")
        if metadata.get("audit_id"):
            tags.append("audit_tagged")
        return tuple(tags)


def classify_mutation_risk(
    *,
    operation_type: str,
    target_path: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> str:
    metadata = dict(metadata or {})
    operation = str(operation_type or "").strip().lower()
    target = str(target_path or "").replace("\\", "/").lower()

    if operation == "external_state_mutation" or metadata.get("external"):
        return "EXTERNAL"
    if operation in {"file_delete", "git_mutation"}:
        return "IRREVERSIBLE"
    if operation in {"patch_apply", "source_code_mutation"}:
        return "HIGH"
    if operation == "config_mutation" or target.endswith((".yaml", ".yml", ".toml", ".ini", ".json")):
        return "HIGH"
    if operation in {"file_write", "generated_artifact_write"}:
        return "MODERATE"
    return "LOW"
