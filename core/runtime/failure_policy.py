from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


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


class FailurePolicy:
    """
    Runtime failure policy table.

    Expected engineering failures such as command/test/compile failures should
    be observable by later steps when a step has continue_on_failure=True.
    They should not automatically retry forever.
    """

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
