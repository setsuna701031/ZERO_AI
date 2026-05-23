from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


EXECUTION_ALLOWED = "allowed"
EXECUTION_BLOCKED = "blocked"
EXECUTION_REVIEW_REQUIRED = "review_required"
EXECUTION_SAFE_MODE = "safe_mode"

ACTION_NONE = "none"
ACTION_BLOCK_TOOL = "block_tool"
ACTION_DISABLE_MUTATION = "disable_mutation"
ACTION_REQUIRE_REVIEW = "require_review"
ACTION_LOWER_AUTONOMY = "lower_autonomy"

POLICY_MODE_NORMAL = "normal"
POLICY_MODE_REVIEW_REQUIRED = "review_required"
POLICY_MODE_SAFE = "safe"
POLICY_MODE_RESTRICTED = "restricted"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimePolicyEnforcementResult:
    execution_status: str
    allowed: bool
    reason: str
    enforcement_action: str
    runtime_mode: str
    step: dict[str, Any] = field(default_factory=dict)
    policy_snapshot: dict[str, Any] = field(default_factory=dict)
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_timestamp)
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.fingerprint:
            object.__setattr__(
                self,
                "fingerprint",
                _stable_fingerprint(self.to_dict(include_fingerprint=False)),
            )

    def to_dict(self, include_fingerprint: bool = True) -> dict[str, Any]:
        payload = {
            "artifact_type": "runtime_policy_enforcement_result",
            "execution_status": self.execution_status,
            "allowed": self.allowed,
            "reason": self.reason,
            "enforcement_action": self.enforcement_action,
            "runtime_mode": self.runtime_mode,
            "step": copy.deepcopy(self.step),
            "policy_snapshot": copy.deepcopy(self.policy_snapshot),
            "audit_events": copy.deepcopy(self.audit_events),
            "created_at": self.created_at,
        }

        if include_fingerprint:
            payload["fingerprint"] = self.fingerprint
            payload["verified"] = self.verify()

        return payload

    def verify(self) -> bool:
        return self.fingerprint == _stable_fingerprint(
            self.to_dict(include_fingerprint=False)
        )


class RuntimePolicyEnforcement:
    """
    Active runtime governance enforcement layer.

    This layer actively gates execution paths according to evolved runtime policy.
    """

    def evaluate_execution(
        self,
        *,
        step: dict[str, Any],
        policy_mode: str,
        applied_actions: list[str],
        autonomy_level: int,
    ) -> RuntimePolicyEnforcementResult:
        step_payload = copy.deepcopy(step if isinstance(step, dict) else {})
        actions = [str(item) for item in applied_actions]

        step_type = str(step_payload.get("type") or "").strip().lower()
        tool_name = str(step_payload.get("tool") or "").strip().lower()

        runtime_mode = str(policy_mode or POLICY_MODE_NORMAL)

        # Block unsafe tools
        if (
            ACTION_BLOCK_TOOL in actions
            and tool_name in {"shell_tool", "terminal_tool", "unsafe_tool"}
        ):
            return self._build_result(
                execution_status=EXECUTION_BLOCKED,
                allowed=False,
                reason="tool_blocked_by_runtime_policy",
                enforcement_action=ACTION_BLOCK_TOOL,
                runtime_mode=runtime_mode,
                step=step_payload,
                policy_snapshot={
                    "policy_mode": runtime_mode,
                    "autonomy_level": autonomy_level,
                    "applied_actions": actions,
                },
            )

        # Disable mutation paths
        if (
            ACTION_DISABLE_MUTATION in actions
            and step_type in {"mutation", "apply_patch", "self_modify"}
        ):
            return self._build_result(
                execution_status=EXECUTION_BLOCKED,
                allowed=False,
                reason="mutation_path_disabled",
                enforcement_action=ACTION_DISABLE_MUTATION,
                runtime_mode=runtime_mode,
                step=step_payload,
                policy_snapshot={
                    "policy_mode": runtime_mode,
                    "autonomy_level": autonomy_level,
                    "applied_actions": actions,
                },
            )

        # Require review under low autonomy / review mode
        if (
            ACTION_REQUIRE_REVIEW in actions
            or runtime_mode == POLICY_MODE_REVIEW_REQUIRED
            or autonomy_level < 70
        ):
            return self._build_result(
                execution_status=EXECUTION_REVIEW_REQUIRED,
                allowed=False,
                reason="execution_requires_review",
                enforcement_action=ACTION_REQUIRE_REVIEW,
                runtime_mode=runtime_mode,
                step=step_payload,
                policy_snapshot={
                    "policy_mode": runtime_mode,
                    "autonomy_level": autonomy_level,
                    "applied_actions": actions,
                },
            )

        # Safe mode runtime
        if runtime_mode == POLICY_MODE_SAFE:
            return self._build_result(
                execution_status=EXECUTION_SAFE_MODE,
                allowed=True,
                reason="runtime_safe_mode_enabled",
                enforcement_action=ACTION_LOWER_AUTONOMY,
                runtime_mode=runtime_mode,
                step=step_payload,
                policy_snapshot={
                    "policy_mode": runtime_mode,
                    "autonomy_level": autonomy_level,
                    "applied_actions": actions,
                },
            )

        return self._build_result(
            execution_status=EXECUTION_ALLOWED,
            allowed=True,
            reason="execution_allowed",
            enforcement_action=ACTION_NONE,
            runtime_mode=runtime_mode,
            step=step_payload,
            policy_snapshot={
                "policy_mode": runtime_mode,
                "autonomy_level": autonomy_level,
                "applied_actions": actions,
            },
        )

    def _build_result(
        self,
        *,
        execution_status: str,
        allowed: bool,
        reason: str,
        enforcement_action: str,
        runtime_mode: str,
        step: dict[str, Any],
        policy_snapshot: dict[str, Any],
    ) -> RuntimePolicyEnforcementResult:
        return RuntimePolicyEnforcementResult(
            execution_status=execution_status,
            allowed=allowed,
            reason=reason,
            enforcement_action=enforcement_action,
            runtime_mode=runtime_mode,
            step=copy.deepcopy(step),
            policy_snapshot=copy.deepcopy(policy_snapshot),
            audit_events=[
                {
                    "event_type": "runtime_policy_enforcement",
                    "execution_status": execution_status,
                    "reason": reason,
                    "runtime_mode": runtime_mode,
                }
            ],
        )


def enforce_runtime_policy(
    *,
    step: dict[str, Any],
    policy_mode: str,
    applied_actions: list[str],
    autonomy_level: int,
) -> RuntimePolicyEnforcementResult:
    runtime = RuntimePolicyEnforcement()

    return runtime.evaluate_execution(
        step=step,
        policy_mode=policy_mode,
        applied_actions=applied_actions,
        autonomy_level=autonomy_level,
    )


__all__ = [
    "RuntimePolicyEnforcement",
    "RuntimePolicyEnforcementResult",
    "EXECUTION_ALLOWED",
    "EXECUTION_BLOCKED",
    "EXECUTION_REVIEW_REQUIRED",
    "EXECUTION_SAFE_MODE",
    "ACTION_NONE",
    "ACTION_BLOCK_TOOL",
    "ACTION_DISABLE_MUTATION",
    "ACTION_REQUIRE_REVIEW",
    "ACTION_LOWER_AUTONOMY",
    "POLICY_MODE_NORMAL",
    "POLICY_MODE_REVIEW_REQUIRED",
    "POLICY_MODE_SAFE",
    "POLICY_MODE_RESTRICTED",
    "enforce_runtime_policy",
]
