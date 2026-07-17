from __future__ import annotations

"""Loop-facing contract for engineering adaptive replan decisions.

AdaptiveReplanContract is the boundary between EngineeringAdaptivePlanner output
and EngineeringGoalLoop orchestration.  The planner may use its own decision
vocabulary, but the loop consumes only this contract.  The contract does not run
runtime actions, persist goals, write evidence, or mutate repositories.
"""

import copy
from dataclasses import dataclass
from typing import Any, Mapping


ADAPTIVE_REPLAN_CONTRACT_SCHEMA = "zero.adaptive_replan_contract.v1"

_TERMINAL_COMPLETE = frozenset({"complete", "completed", "success", "succeeded"})
_TERMINAL_BLOCKED = frozenset({"blocked", "block", "stop_with_root_cause"})
_REPLAN = frozenset({"replan", "request_replan", "retry_with_replan"})
_CONTINUE = frozenset({"continue", "continue_current_plan", "create_followup_goal", "followup", "continue_active"})
_WAIT = frozenset({"wait", "waiting", "wait_for_user", "request_user_review"})
_STOP = frozenset({"stop", "no_action", "non_continuable", "halt"})


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _limit(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return max(0, int(default))


@dataclass(frozen=True)
class AdaptiveReplanContract:
    """A passive contract consumed by EngineeringGoalLoop.

    loop_action is the only field the loop should branch on.  decision is kept
    for audit/debugging and to preserve the planner's original language.
    """

    decision: str
    loop_action: str
    terminal: bool
    stop_reason: str
    reason: str
    refusal_reason: str = ""
    requires_replan: bool = False
    creates_replan_record: bool = False
    creates_continuation: bool = False
    persists_adaptive_record: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision", _text(self.decision, "unavailable"))
        object.__setattr__(self, "loop_action", _text(self.loop_action, "stop"))
        object.__setattr__(self, "stop_reason", _text(self.stop_reason))
        object.__setattr__(self, "reason", _text(self.reason, self.stop_reason or self.loop_action))
        object.__setattr__(self, "refusal_reason", _text(self.refusal_reason))
        object.__setattr__(self, "terminal", bool(self.terminal))
        object.__setattr__(self, "requires_replan", bool(self.requires_replan))
        object.__setattr__(self, "creates_replan_record", bool(self.creates_replan_record))
        object.__setattr__(self, "creates_continuation", bool(self.creates_continuation))
        object.__setattr__(self, "persists_adaptive_record", bool(self.persists_adaptive_record))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ADAPTIVE_REPLAN_CONTRACT_SCHEMA,
            "decision": self.decision,
            "loop_action": self.loop_action,
            "terminal": self.terminal,
            "stop_reason": self.stop_reason,
            "reason": self.reason,
            "refusal_reason": self.refusal_reason,
            "requires_replan": self.requires_replan,
            "creates_replan_record": self.creates_replan_record,
            "creates_continuation": self.creates_continuation,
            "persists_adaptive_record": self.persists_adaptive_record,
            "execution_path": {
                "decision_only": True,
                "executes_tasks": False,
                "persists_records": False,
                "mutates_goal_repository": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }


def normalize_engineering_adaptive_decision(decision: Any) -> str:
    """Normalize planner decisions without changing planner ownership."""

    raw = _text(decision).lower()
    if raw in _TERMINAL_COMPLETE:
        return "complete"
    if raw in _TERMINAL_BLOCKED:
        return "blocked"
    if raw in _REPLAN:
        return "replan"
    if raw in _CONTINUE:
        return "continue"
    if raw in _WAIT:
        return "wait_for_user"
    if raw in _STOP:
        return "stop"
    return raw or "unavailable"


def build_adaptive_replan_contract(
    *,
    cycle: Mapping[str, Any],
    replan_count: int = 0,
    continuation_count: int = 0,
    max_replans: int = 1,
    max_continuations: int = 3,
) -> AdaptiveReplanContract:
    """Translate a cycle's adaptive decision into a loop-facing contract."""

    cycle_record = _mapping(cycle)
    adaptive = _mapping(cycle_record.get("adaptive_decision_record"))
    original_decision = _text(cycle_record.get("adaptive_decision") or adaptive.get("decision"), "unavailable")
    decision = normalize_engineering_adaptive_decision(original_decision)
    reason = _text(
        cycle_record.get("decision_reason")
        or adaptive.get("decision_reason")
        or adaptive.get("reason")
        or cycle_record.get("adaptive_reason"),
        f"adaptive_decision_{decision}",
    )
    replans = _limit(replan_count)
    continuations = _limit(continuation_count)
    replan_limit = _limit(max_replans)
    continuation_limit = _limit(max_continuations)

    if decision == "complete":
        return AdaptiveReplanContract(
            decision=original_decision,
            loop_action="complete",
            terminal=True,
            stop_reason="complete",
            reason=reason,
        )

    if decision == "blocked":
        return AdaptiveReplanContract(
            decision=original_decision,
            loop_action="blocked",
            terminal=True,
            stop_reason="blocked",
            reason=reason,
        )

    if decision == "replan":
        if replans >= replan_limit:
            return AdaptiveReplanContract(
                decision=original_decision,
                loop_action="refuse",
                terminal=True,
                stop_reason="max_replans_exhausted",
                refusal_reason="max_replans_exhausted",
                reason="max_replans_exhausted",
                requires_replan=True,
            )
        return AdaptiveReplanContract(
            decision=original_decision,
            loop_action="replan",
            terminal=True,
            stop_reason="replan",
            reason=reason,
            requires_replan=True,
            creates_replan_record=True,
        )

    if decision == "continue":
        if continuations >= continuation_limit:
            return AdaptiveReplanContract(
                decision=original_decision,
                loop_action="refuse",
                terminal=True,
                stop_reason="max_continuations_exhausted",
                refusal_reason="max_continuations_exhausted",
                reason="max_continuations_exhausted",
                creates_continuation=False,
            )
        return AdaptiveReplanContract(
            decision=original_decision,
            loop_action="continue",
            terminal=False,
            stop_reason="",
            reason=reason,
            creates_continuation=True,
        )

    if decision == "wait_for_user":
        return AdaptiveReplanContract(
            decision=original_decision,
            loop_action="wait_for_user",
            terminal=True,
            stop_reason="wait_for_user",
            refusal_reason="wait_for_user",
            reason=reason,
        )

    return AdaptiveReplanContract(
        decision=original_decision,
        loop_action="stop",
        terminal=True,
        stop_reason="non_continuable_adaptive_decision",
        refusal_reason="non_continuable_adaptive_decision",
        reason=reason,
    )


__all__ = [
    "ADAPTIVE_REPLAN_CONTRACT_SCHEMA",
    "AdaptiveReplanContract",
    "build_adaptive_replan_contract",
    "normalize_engineering_adaptive_decision",
]
