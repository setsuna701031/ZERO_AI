from __future__ import annotations

"""Passive contract between EngineeringGoalRunner and EngineeringGoalLoop.

EngineeringRuntimeContract is the boundary object that carries one completed
runtime pass plus the post-runtime adaptive decision.  It does not execute
runtime work, decide adaptive actions, persist goals, write evidence, or mutate
memory.  Runner produces this contract; Loop consumes this contract.
"""

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.runtime.runtime_result_projection import mapping_projection


ENGINEERING_RUNTIME_CONTRACT_SCHEMA = "zero.engineering_runtime_contract.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return mapping_projection(value, max_depth=5, max_items=40, max_string_chars=4096)


@dataclass(frozen=True)
class EngineeringRuntimeContract:
    """Runner-to-loop handoff for one engineering runtime pass."""

    goal_id: str
    action: str
    ok: bool
    runtime_request: Mapping[str, Any] = field(default_factory=dict)
    runtime_result: Mapping[str, Any] = field(default_factory=dict)
    runtime_stdout: str = ""
    runtime_root_cause: Mapping[str, Any] = field(default_factory=dict)
    adaptive_decision: Mapping[str, Any] = field(default_factory=dict)
    issue_summary: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "goal_id", _clean_text(self.goal_id))
        object.__setattr__(self, "action", _clean_text(self.action, "run_goal"))
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "runtime_request", _as_mapping(self.runtime_request))
        object.__setattr__(self, "runtime_result", _as_mapping(self.runtime_result))
        object.__setattr__(self, "runtime_stdout", str(self.runtime_stdout or ""))
        object.__setattr__(self, "runtime_root_cause", _as_mapping(self.runtime_root_cause))
        object.__setattr__(self, "adaptive_decision", _as_mapping(self.adaptive_decision))
        object.__setattr__(self, "issue_summary", _as_mapping(self.issue_summary))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ENGINEERING_RUNTIME_CONTRACT_SCHEMA,
            "goal_id": self.goal_id,
            "action": self.action,
            "ok": self.ok,
            "runtime_request": copy.deepcopy(dict(self.runtime_request)),
            "runtime_result": copy.deepcopy(dict(self.runtime_result)),
            "runtime_stdout": self.runtime_stdout,
            "runtime_root_cause": copy.deepcopy(dict(self.runtime_root_cause)),
            "adaptive_decision": copy.deepcopy(dict(self.adaptive_decision)),
            "issue_summary": copy.deepcopy(dict(self.issue_summary)),
            "execution_path": {
                "runner_produces_contract": True,
                "loop_consumes_contract": True,
                "decision_only": True,
                "executes_tasks": False,
                "persists_goal": False,
                "writes_evidence": False,
                "mutates_runtime": False,
                "mutates_memory": False,
            },
        }


def build_engineering_runtime_contract(
    *,
    goal_id: str,
    action: str,
    ok: bool,
    runtime_request: Mapping[str, Any] | None = None,
    runtime_result: Mapping[str, Any] | None = None,
    runtime_stdout: str = "",
    runtime_root_cause: Mapping[str, Any] | None = None,
    adaptive_decision: Mapping[str, Any] | None = None,
    issue_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a passive runner-to-loop contract from explicit fields."""

    return EngineeringRuntimeContract(
        goal_id=goal_id,
        action=action,
        ok=ok,
        runtime_request=runtime_request or {},
        runtime_result=runtime_result or {},
        runtime_stdout=runtime_stdout,
        runtime_root_cause=runtime_root_cause or {},
        adaptive_decision=adaptive_decision or {},
        issue_summary=issue_summary or {},
    ).to_dict()


def build_engineering_runtime_contract_from_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a runner result into EngineeringRuntimeContract.

    This supports both new runner output that already includes the contract and
    older runner output that still exposes runtime/adaptive fields directly.
    """

    record = _as_mapping(result)
    existing = _as_mapping(record.get("engineering_runtime_contract"))
    if existing.get("schema") == ENGINEERING_RUNTIME_CONTRACT_SCHEMA:
        return copy.deepcopy(existing)
    return build_engineering_runtime_contract(
        goal_id=_clean_text(record.get("goal_id")),
        action=_clean_text(record.get("action"), "run_goal"),
        ok=bool(record.get("ok")),
        runtime_request=_as_mapping(record.get("runtime_request")),
        runtime_result=_as_mapping(record.get("runtime_result")),
        runtime_stdout=str(record.get("runtime_stdout") or ""),
        runtime_root_cause=_as_mapping(record.get("runtime_root_cause")),
        adaptive_decision=_as_mapping(record.get("adaptive_decision")),
        issue_summary=_as_mapping(record.get("issue_summary")),
    )


__all__ = [
    "ENGINEERING_RUNTIME_CONTRACT_SCHEMA",
    "EngineeringRuntimeContract",
    "build_engineering_runtime_contract",
    "build_engineering_runtime_contract_from_result",
]
