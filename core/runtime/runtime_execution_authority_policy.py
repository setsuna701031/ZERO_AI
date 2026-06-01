from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping


CANONICAL_EXECUTION_AUTHORITY_PATH = (
    "runtime.execution_gateway",
    "runtime.executor",
)

CANONICAL_EXECUTION_OWNERS = {
    "runtime.execution_gateway",
    "core.runtime.execution_gateway",
    "runtime.executor",
    "core.runtime.executor",
}

ORCHESTRATION_ONLY_OWNERS = {
    "scheduler",
    "core.tasks.scheduler",
    "agent_loop",
    "core.agent.agent_loop",
    "system_boot",
    "services.system_boot",
}

SIDE_EFFECT_ACTIONS = {
    "command",
    "subprocess",
    "shell",
    "run_python",
    "write_file",
    "append_file",
    "apply_patch",
    "apply_unified_diff",
    "mutation",
    "recovery",
    "transition",
    "file_mutation",
    "patch_apply",
    "command_execution",
}


@dataclass(frozen=True)
class RuntimeExecutionAuthorityDecision:
    allowed: bool
    blocked: bool
    decision_id: str
    source: str
    action_type: str
    reason: str
    canonical_path: tuple[str, ...] = CANONICAL_EXECUTION_AUTHORITY_PATH
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "runtime_execution_authority_decision.v1",
            "allowed": self.allowed,
            "blocked": self.blocked,
            "decision_id": self.decision_id,
            "source": self.source,
            "action_type": self.action_type,
            "reason": self.reason,
            "canonical_path": list(self.canonical_path),
            "evidence": copy.deepcopy(self.evidence),
        }


class RuntimeExecutionAuthorityPolicy:
    """Policy-only execution authority closure.

    The policy decides whether a side-effecting execution request is already on
    the canonical execution path. It does not run commands, mutate files,
    schedule work, or recover/repair tasks.
    """

    def evaluate(
        self,
        *,
        source: Any,
        action_type: Any,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeExecutionAuthorityDecision:
        normalized_source = _normalize_source(source)
        normalized_action = _normalize_action(action_type)
        meta = copy.deepcopy(dict(metadata or {}))
        side_effect = _is_side_effect(normalized_action, meta)

        if not side_effect:
            return _decision(
                allowed=True,
                source=normalized_source,
                action_type=normalized_action,
                reason="non_side_effect_action",
                metadata=meta,
            )

        if normalized_source in CANONICAL_EXECUTION_OWNERS:
            return _decision(
                allowed=True,
                source=normalized_source,
                action_type=normalized_action,
                reason="canonical_execution_authority",
                metadata=meta,
            )

        if normalized_source in ORCHESTRATION_ONLY_OWNERS:
            return _decision(
                allowed=False,
                source=normalized_source,
                action_type=normalized_action,
                reason="orchestration_surface_cannot_execute_side_effect",
                metadata=meta,
            )

        if _looks_like_helper_or_bridge(normalized_source):
            return _decision(
                allowed=False,
                source=normalized_source,
                action_type=normalized_action,
                reason="helper_bridge_cannot_execute_side_effect",
                metadata=meta,
            )

        return _decision(
            allowed=False,
            source=normalized_source,
            action_type=normalized_action,
            reason="non_canonical_execution_authority",
            metadata=meta,
        )


def evaluate_execution_authority(
    *,
    source: Any,
    action_type: Any,
    metadata: Mapping[str, Any] | None = None,
) -> RuntimeExecutionAuthorityDecision:
    return RuntimeExecutionAuthorityPolicy().evaluate(
        source=source,
        action_type=action_type,
        metadata=metadata,
    )


def _decision(
    *,
    allowed: bool,
    source: str,
    action_type: str,
    reason: str,
    metadata: Mapping[str, Any],
) -> RuntimeExecutionAuthorityDecision:
    evidence = {
        "source": source,
        "action_type": action_type,
        "metadata": copy.deepcopy(dict(metadata)),
        "canonical_path": list(CANONICAL_EXECUTION_AUTHORITY_PATH),
        "side_effect": _is_side_effect(action_type, metadata),
        "no_execution_performed": True,
    }
    decision_id = "runtime-execution-authority-" + _fingerprint(
        {
            "allowed": allowed,
            "source": source,
            "action_type": action_type,
            "reason": reason,
            "metadata": metadata,
        }
    )[:16]
    return RuntimeExecutionAuthorityDecision(
        allowed=bool(allowed),
        blocked=not bool(allowed),
        decision_id=decision_id,
        source=source,
        action_type=action_type,
        reason=reason,
        evidence=evidence,
    )


def _is_side_effect(action_type: str, metadata: Mapping[str, Any]) -> bool:
    if action_type in SIDE_EFFECT_ACTIONS:
        return True
    if bool(metadata.get("side_effect")):
        return True
    effect_type = str(metadata.get("effect_type") or "").strip().lower()
    return effect_type in SIDE_EFFECT_ACTIONS


def _looks_like_helper_or_bridge(source: str) -> bool:
    tokens = ("helper", "bridge", "adapter", "tool", "task_runner")
    return any(token in source for token in tokens)


def _normalize_source(value: Any) -> str:
    return str(value or "").strip().replace("/", ".").replace("\\", ".").lower()


def _normalize_action(value: Any) -> str:
    return str(value or "").strip().lower()


def _fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "CANONICAL_EXECUTION_AUTHORITY_PATH",
    "CANONICAL_EXECUTION_OWNERS",
    "ORCHESTRATION_ONLY_OWNERS",
    "RuntimeExecutionAuthorityDecision",
    "RuntimeExecutionAuthorityPolicy",
    "SIDE_EFFECT_ACTIONS",
    "evaluate_execution_authority",
]
