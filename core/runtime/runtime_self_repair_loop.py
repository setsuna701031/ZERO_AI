from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Mapping


RUNTIME_SELF_REPAIR_LOOP_SCHEMA = "zero.runtime.self_repair_loop.v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return deepcopy(value)
    if isinstance(value, tuple):
        return list(deepcopy(value))
    return []


def _result_ok(result: Mapping[str, Any]) -> bool:
    payload = _mapping(result)

    if payload.get("ok") is not True:
        return False

    operator_result = _mapping(payload.get("operator_result"))
    if operator_result:
        controlled_mutation_result = _mapping(
            operator_result.get("controlled_mutation_result")
        )

        if controlled_mutation_result:
            return (
                controlled_mutation_result.get("ok") is True
                and controlled_mutation_result.get("validation_passed") is True
                and controlled_mutation_result.get("mutation_completed") is True
            )

        if operator_result.get("validation_passed") is False:
            return False

    return True


def _denial_reason(result: Mapping[str, Any]) -> str:
    payload = _mapping(result)

    candidates = [
        payload.get("denial_reason"),
        _mapping(payload.get("operator_result")).get("denial_reason"),
        _mapping(
            _mapping(payload.get("operator_result")).get(
                "controlled_mutation_result"
            )
        ).get("denial_reason"),
    ]

    for candidate in candidates:
        text = _text(candidate)
        if text:
            return text

    return ""


def _non_mainline_issues(result: Mapping[str, Any]) -> list[str]:
    payload = _mapping(result)
    issues: list[str] = []

    for item in _list(payload.get("non_mainline_issues")):
        issues.append(str(item))

    operator_result = _mapping(payload.get("operator_result"))
    for item in _list(operator_result.get("non_mainline_issues")):
        issues.append(str(item))

    controlled_mutation_result = _mapping(
        operator_result.get("controlled_mutation_result")
    )
    for item in _list(controlled_mutation_result.get("non_mainline_issues")):
        issues.append(str(item))

    governed_runtime_result = _mapping(
        operator_result.get("governed_runtime_result")
    )
    for item in _list(governed_runtime_result.get("non_mainline_issues")):
        issues.append(str(item))

    return issues


def _strip_failure_injection(text: str) -> str:
    lowered = _text(text)
    marker = " force validation failure"
    if lowered.lower().endswith(marker):
        return lowered[: -len(marker)].strip()
    return lowered


def build_repair_task(
    natural_task: Any,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    task_text = _text(natural_task)
    safe_task = _strip_failure_injection(task_text)
    denial = _denial_reason(result)
    issues = _non_mainline_issues(result)

    repair_goal = safe_task
    if not repair_goal:
        repair_goal = "repair failed controlled mutation"

    return {
        "schema": RUNTIME_SELF_REPAIR_LOOP_SCHEMA,
        "ok": True,
        "repair_required": True,
        "repair_goal": repair_goal,
        "source_goal": task_text,
        "denial_reason": denial,
        "non_mainline_issues": issues,
        "repair_strategy": "retry_without_failure_injection",
    }


@dataclass(frozen=True)
class RuntimeSelfRepairLoop:
    runner: Callable[[str], Mapping[str, Any]]
    max_attempts: int = 2

    def run(self, natural_task: Any) -> dict[str, Any]:
        goal = _text(natural_task)
        attempts: list[dict[str, Any]] = []

        if not goal:
            return {
                "schema": RUNTIME_SELF_REPAIR_LOOP_SCHEMA,
                "ok": False,
                "loop_status": "denied",
                "denial_reason": "natural_task_required",
                "attempts": attempts,
                "repair_attempted": False,
                "final_goal": "",
                "final_result": {},
            }

        current_goal = goal
        repair_attempted = False

        for attempt_number in range(1, max(1, self.max_attempts) + 1):
            raw_result = self.runner(current_goal)
            result = _mapping(raw_result)

            attempt = {
                "attempt_number": attempt_number,
                "goal": current_goal,
                "ok": _result_ok(result),
                "result": result,
                "denial_reason": _denial_reason(result),
                "non_mainline_issues": _non_mainline_issues(result),
            }
            attempts.append(attempt)

            if attempt["ok"] is True:
                return {
                    "schema": RUNTIME_SELF_REPAIR_LOOP_SCHEMA,
                    "ok": True,
                    "loop_status": (
                        "repaired" if repair_attempted else "completed"
                    ),
                    "attempts": attempts,
                    "repair_attempted": repair_attempted,
                    "final_goal": current_goal,
                    "final_result": result,
                }

            if attempt_number >= max(1, self.max_attempts):
                break

            repair = build_repair_task(current_goal, result)
            current_goal = _text(repair.get("repair_goal"))
            repair_attempted = True

        return {
            "schema": RUNTIME_SELF_REPAIR_LOOP_SCHEMA,
            "ok": False,
            "loop_status": "failed",
            "attempts": attempts,
            "repair_attempted": repair_attempted,
            "final_goal": current_goal,
            "final_result": attempts[-1]["result"] if attempts else {},
            "denial_reason": attempts[-1]["denial_reason"] if attempts else "",
            "non_mainline_issues": (
                attempts[-1]["non_mainline_issues"] if attempts else []
            ),
        }


__all__ = [
    "RUNTIME_SELF_REPAIR_LOOP_SCHEMA",
    "RuntimeSelfRepairLoop",
    "build_repair_task",
]
