from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Literal


FailureType = Literal[
    "transient_error",
    "tool_error",
    "validation_error",
    "dependency_unmet",
    "unsafe_action",
    "cancelled",
    "unknown",
    "python_failed",
    "python_path_missing",
    "python_executable_missing",
    "run_python_command_parse_failed",
    "run_python_command_not_python",
    "file_not_found",
    "path_resolve_failed",
    "verify_failed",
    "regression_verify_failed",
]


@dataclass
class FailureDecision:
    retry: bool = False
    replan: bool = False
    fail: bool = False
    wait: bool = False


@dataclass
class RepairPolicyDecision:
    """Decision for autonomous repair injection governance."""

    allow: bool = True
    action: str = "allow"
    reason: str = "repair allowed"
    risk_level: str = "low"
    requires_review: bool = False
    quarantine: bool = False
    max_repair_depth: int = 1
    current_repair_depth: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FailurePolicy:
    """
    Runtime failure policy table.

    Expected engineering failures such as command/test/compile failures should
    be observable by later steps when a step has continue_on_failure=True.
    They should not automatically retry forever.
    """

    CRITICAL_REPAIR_PATH_PREFIXES = (
        "core/",
        "services/",
        "app.py",
        "pyproject.toml",
        "requirements.txt",
        ".github/",
    )

    POLICY_TABLE = {
        # Generic runtime
        "transient_error": FailureDecision(retry=True),
        "tool_error": FailureDecision(retry=True, replan=True),
        "validation_error": FailureDecision(replan=True),
        "dependency_unmet": FailureDecision(wait=True),
        "unsafe_action": FailureDecision(fail=True),
        "cancelled": FailureDecision(fail=True),

        # Engineering runtime
        "python_failed": FailureDecision(retry=False, replan=False, fail=False),
        "python_path_missing": FailureDecision(retry=False, replan=False, fail=True),
        "python_executable_missing": FailureDecision(retry=False, replan=False, fail=True),
        "run_python_command_parse_failed": FailureDecision(retry=False, replan=False, fail=True),
        "run_python_command_not_python": FailureDecision(retry=False, replan=False, fail=True),
        "file_not_found": FailureDecision(retry=False, replan=False, fail=False),
        "path_resolve_failed": FailureDecision(retry=False, replan=False, fail=True),
        "verify_failed": FailureDecision(retry=False, replan=False, fail=False),
        "regression_verify_failed": FailureDecision(retry=False, replan=False, fail=False),

        # Fallback remains conservative
        "unknown": FailureDecision(retry=True, replan=True),
    }

    @classmethod
    def decide(cls, failure_type: FailureType) -> FailureDecision:
        return cls.POLICY_TABLE.get(
            failure_type,
            FailureDecision(retry=True, replan=True),
        )

    @classmethod
    def decide_repair(
        cls,
        *,
        task: Dict[str, Any] | None = None,
        state: Dict[str, Any] | None = None,
        step: Dict[str, Any] | None = None,
        step_result: Dict[str, Any] | None = None,
        source_path: str = "",
    ) -> RepairPolicyDecision:
        """Govern whether autonomous repair may inject new runtime steps.

        v1 policy boundaries:
        - Never recursively repair an injected repair step.
        - Enforce a bounded repair depth / injection ceiling.
        - Quarantine after rollback hard-failure.
        - Require review for critical repo paths.
        - Keep normal sandbox compile repairs allowed.
        """

        task = task if isinstance(task, dict) else {}
        state = state if isinstance(state, dict) else {}
        step = step if isinstance(step, dict) else {}
        step_result = step_result if isinstance(step_result, dict) else {}

        repair_context = state.get("repair_context")
        if not isinstance(repair_context, dict):
            repair_context = task.get("repair_context")
        if not isinstance(repair_context, dict):
            repair_context = {}

        if bool(step.get("repair_injected") or step.get("repair_generated")):
            return RepairPolicyDecision(
                allow=False,
                action="fail",
                reason="recursive repair step blocked",
                risk_level="high",
                quarantine=True,
            )

        rollback_result = repair_context.get("rollback_result")
        if isinstance(rollback_result, dict) and rollback_result and rollback_result.get("ok") is False:
            return RepairPolicyDecision(
                allow=False,
                action="fail",
                reason="rollback failure quarantine",
                risk_level="high",
                quarantine=True,
            )

        max_depth_raw = (
            task.get("max_repair_depth")
            or task.get("max_repair_injections")
            or state.get("max_repair_depth")
            or state.get("max_repair_injections")
            or 1
        )
        try:
            max_depth = max(1, int(max_depth_raw))
        except Exception:
            max_depth = 1

        injections = repair_context.get("injections")
        current_depth = len(injections) if isinstance(injections, list) else 0
        if current_depth >= max_depth:
            return RepairPolicyDecision(
                allow=False,
                action="fail",
                reason="max repair depth reached",
                risk_level="medium",
                max_repair_depth=max_depth,
                current_repair_depth=current_depth,
            )

        target_text = str(
            source_path
            or step.get("repair_source_path")
            or step.get("source_path")
            or step.get("target_path")
            or step.get("path")
            or ""
        ).replace("\\", "/").lstrip("/")

        lowered = target_text.lower()
        if lowered:
            for prefix in cls.CRITICAL_REPAIR_PATH_PREFIXES:
                normalized_prefix = str(prefix).lower()
                if lowered == normalized_prefix.rstrip("/") or lowered.startswith(normalized_prefix):
                    return RepairPolicyDecision(
                        allow=False,
                        action="review_required",
                        reason="critical repo path requires review",
                        risk_level="high",
                        requires_review=True,
                        max_repair_depth=max_depth,
                        current_repair_depth=current_depth,
                    )

        return RepairPolicyDecision(
            allow=True,
            action="allow",
            reason="repair allowed",
            risk_level="low",
            max_repair_depth=max_depth,
            current_repair_depth=current_depth,
        )
