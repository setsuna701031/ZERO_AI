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
]


@dataclass
class FailureDecision:
    retry: bool = False
    replan: bool = False
    fail: bool = False
    wait: bool = False


class FailurePolicy:
    """
    Decide what to do after a step failure.
    This is the core policy of Agent runtime.
    """

    POLICY_TABLE = {
        "transient_error": FailureDecision(retry=True),
        "tool_error": FailureDecision(retry=True, replan=True),
        "validation_error": FailureDecision(replan=True),
        "dependency_unmet": FailureDecision(wait=True),
        "unsafe_action": FailureDecision(fail=True),
        "cancelled": FailureDecision(fail=True),
        "unknown": FailureDecision(retry=True, replan=True),
    }

    @classmethod
    def decide(cls, failure_type: FailureType) -> FailureDecision:
        return cls.POLICY_TABLE.get(
            failure_type,
            FailureDecision(retry=True, replan=True),
        )