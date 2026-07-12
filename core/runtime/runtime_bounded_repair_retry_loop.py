from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Mapping


RUNTIME_BOUNDED_REPAIR_RETRY_LOOP_SCHEMA = (
    "zero.runtime.bounded_repair_retry_loop.v1"
)
_NEVER_RETRY = {
    "path_safety_failure",
    "adapter_unavailable",
    "adapter_incomplete",
    "rollback_failure",
    "observation_failure",
    "evidence_parse_failure",
    "unknown_failure",
}
_DEFAULT_RETRYABLE = {"validation_failure", "mutation_failure"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _task(task: Any) -> dict[str, Any]:
    if isinstance(task, str):
        return {"goal": _text(task), "task_id": "", "metadata": {}}
    payload = _mapping(task)
    return {
        "goal": _text(payload.get("goal")),
        "task_id": _text(payload.get("task_id")),
        "metadata": _mapping(payload.get("metadata")),
    }


def _reference(task: Any, normalized: Mapping[str, Any]) -> str:
    if _text(normalized.get("task_id")):
        return _text(normalized.get("task_id"))
    body = json.dumps(task, ensure_ascii=False, sort_keys=True, default=str)
    return f"bounded-retry-task-{sha256(body.encode('utf-8')).hexdigest()[:16]}"


def _nested_first(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        if key in value:
            return value[key]
        for child in value.values():
            if isinstance(child, (Mapping, list, tuple)):
                found = _nested_first(child, key, default)
                if found is not default:
                    return found
    elif isinstance(value, (list, tuple)):
        for child in value:
            found = _nested_first(child, key, default)
            if found is not default:
                return found
    return default


def _changed_files(result: Mapping[str, Any]) -> list[str]:
    value = _nested_first(result, "changed_files", [])
    return (
        [_text(item) for item in value if _text(item)]
        if isinstance(value, (list, tuple)) else []
    )


def _completed(result: Mapping[str, Any]) -> bool:
    if "task_completed" in result:
        return result.get("task_completed") is True
    if result.get("ok") is not True:
        return False
    controlled = _mapping(_nested_first(result, "controlled_mutation_result", {}))
    if controlled:
        return (
            controlled.get("ok") is True
            and controlled.get("mutation_completed") is True
            and controlled.get("validation_passed") is True
        )
    return True


def _safe_advisor_error(error_type: str) -> dict[str, Any]:
    return {
        "schema": "zero.runtime.repair_advisor.v1",
        "ok": False,
        "advisor_status": "advisor_error",
        "repair_needed": False,
        "repairability": "insufficient_evidence",
        "failure_category": "unknown_failure",
        "failure_reasons": [f"advisor_error:{error_type}"],
        "repair_execution_allowed": False,
        "autonomous_retry_allowed": False,
        "patch_generation_allowed": False,
        "mutation_allowed": False,
        "requested_changes_modified": False,
    }


@dataclass(frozen=True)
class RuntimeBoundedRepairRetryLoop:
    task_runner: Any
    observer: Any = None
    repair_advisor: Any = None
    max_attempts: int = 2
    stop_on_success: bool = True
    allow_bounded_retry: bool = False
    allow_runner_exception_retry: bool = False

    def _run(self, goal: str) -> Mapping[str, Any]:
        if callable(self.task_runner):
            return self.task_runner(goal)
        run = getattr(self.task_runner, "run", None)
        if callable(run):
            return run(goal)
        raise TypeError("task_runner_not_callable")

    def _observe(
        self, goal: str, task_id: str, changed: list[str], result: Mapping[str, Any]
    ) -> dict[str, Any]:
        if self.observer is None:
            return {}
        observe = self.observer if callable(self.observer) else getattr(self.observer, "observe", None)
        if not callable(observe):
            raise TypeError("observer_not_callable")
        return _mapping(observe(
            goal=goal, task_id=task_id, changed_files=deepcopy(changed),
            runner_result=_mapping(result),
        ))

    def _advise(
        self,
        goal: str,
        task_id: str,
        result: Mapping[str, Any],
        observation: Mapping[str, Any],
        metadata: Mapping[str, Any],
    ) -> dict[str, Any]:
        if self.repair_advisor is None:
            return {}
        advise = self.repair_advisor if callable(self.repair_advisor) else getattr(self.repair_advisor, "advise", None)
        if not callable(advise):
            raise TypeError("repair_advisor_not_callable")
        package_metadata = _mapping(_mapping(result.get("package")).get("metadata"))
        result_metadata = _mapping(result.get("metadata"))

        def source(key: str) -> dict[str, Any]:
            return _mapping(result_metadata.get(key, package_metadata.get(key, metadata.get(key))))

        return _mapping(advise(
            goal=goal,
            task_id=task_id,
            runner_result=_mapping(result),
            workspace_observation=_mapping(observation),
            memory_context=source("memory_context"),
            decision_advice=source("decision_advice"),
            planner_advisor_bridge=source("planner_advisor_bridge"),
        ))

    def _admission(self, *, completed: bool, advice: Mapping[str, Any], attempt: int) -> tuple[bool, str]:
        if completed:
            return False, "task_completed"
        if attempt >= self.max_attempts:
            return False, "max_attempts_reached"
        if not self.allow_bounded_retry:
            return False, "bounded_retry_not_explicitly_allowed"
        if not advice:
            return False, "repair_advisor_unavailable"
        if advice.get("advisor_status") == "advisor_error":
            return False, "repair_advisor_error"
        if advice.get("repair_needed") is not True:
            return False, "repair_not_needed"
        if advice.get("repair_execution_allowed") is not False:
            return False, "repair_execution_boundary_invalid"
        if advice.get("autonomous_retry_allowed") is not False:
            return False, "advisor_retry_boundary_invalid"
        category = _text(advice.get("failure_category"))
        if category in _NEVER_RETRY:
            return False, f"failure_category_not_retryable:{category}"
        if category == "runner_exception":
            if not self.allow_runner_exception_retry:
                return False, "runner_exception_retry_not_allowed"
        elif category not in _DEFAULT_RETRYABLE:
            return False, f"failure_category_not_retryable:{category}"
        if advice.get("repairability") != "likely_repairable":
            return False, "repairability_not_likely_repairable"
        return True, ""

    def _final(
        self,
        *,
        status: str,
        original_goal: str,
        max_attempts: int,
        attempts: list[dict[str, Any]],
        stopped_reason: str,
    ) -> dict[str, Any]:
        final = attempts[-1] if attempts else {}
        completed = final.get("task_completed") is True
        return {
            "schema": RUNTIME_BOUNDED_REPAIR_RETRY_LOOP_SCHEMA,
            "ok": completed,
            "loop_status": status,
            "controlled": True,
            "original_goal": original_goal,
            "goal_mutation_allowed": False,
            "requested_changes_modified": False,
            "autonomous_task_creation": False,
            "patch_generation_allowed": False,
            "repair_execution_allowed": False,
            "bounded_retry_enabled": self.allow_bounded_retry,
            "max_attempts": max_attempts,
            "attempts_completed": len(attempts),
            "retry_count": max(0, len(attempts) - 1),
            "task_completed": completed,
            "runner_ok": final.get("runner_ok") is True,
            "changed_files": deepcopy(final.get("changed_files") or []),
            "denial_reason": _text(final.get("denial_reason")),
            "error_type": _text(final.get("error_type")),
            "workspace_observation": _mapping(final.get("workspace_observation")),
            "repair_advice": _mapping(final.get("repair_advice")),
            "activity_recorded": final.get("activity_recorded") is True,
            "stopped_reason": stopped_reason,
            "attempt_results": attempts,
            "runtime_loop_closed": True,
        }

    def run(self, task: Any) -> dict[str, Any]:
        original = deepcopy(task)
        normalized = _task(original)
        goal = normalized["goal"]
        reference = _reference(original, normalized)
        if not isinstance(self.max_attempts, int) or self.max_attempts < 1 or not goal:
            return self._final(
                status="denied_invalid_configuration",
                original_goal=goal,
                max_attempts=self.max_attempts,
                attempts=[],
                stopped_reason="invalid_configuration",
            )

        attempts: list[dict[str, Any]] = []
        for attempt_number in range(1, self.max_attempts + 1):
            started = _utc_now()
            error_type = ""
            try:
                result = _mapping(self._run(goal))
            except Exception as exc:
                error_type = type(exc).__name__
                result = {
                    "ok": False,
                    "task_completed": False,
                    "denial_reason": f"runner_error:{error_type}",
                    "error_type": error_type,
                }
            changed = _changed_files(result)
            try:
                observation = self._observe(goal, reference, changed, result)
            except Exception as exc:
                observation = {
                    "observer_status": "observer_error",
                    "observation_complete": False,
                    "issues": [f"observer_error:{type(exc).__name__}"],
                }
            try:
                advice = self._advise(
                    goal, reference, result, observation, normalized["metadata"]
                )
            except Exception as exc:
                advice = _safe_advisor_error(type(exc).__name__)

            completed = _completed(result)
            admitted, denial = self._admission(
                completed=completed, advice=advice, attempt=attempt_number
            )
            attempt = {
                "attempt": attempt_number,
                "task_id": reference,
                "task_reference": reference,
                "original_goal": goal,
                "executed_goal": goal,
                "goal_unchanged": True,
                "metadata": deepcopy(normalized["metadata"]),
                "runner_ok": result.get("ok") is True,
                "task_completed": completed,
                "changed_files": changed,
                "denial_reason": _text(_nested_first(result, "denial_reason", "")),
                "error_type": error_type or _text(_nested_first(result, "error_type", "")),
                "activity_recorded": _nested_first(result, "activity_recorded", False) is True,
                "workspace_observation": observation,
                "repair_advice": advice,
                "retry_admitted": admitted,
                "retry_denial_reason": denial,
                "started_at": started,
                "completed_at": _utc_now(),
            }
            attempts.append(attempt)

            if completed:
                return self._final(
                    status="completed" if attempt_number == 1 else "completed_after_retry",
                    original_goal=goal,
                    max_attempts=self.max_attempts,
                    attempts=attempts,
                    stopped_reason="task_completed",
                )
            if not admitted:
                if error_type:
                    status = "runner_error"
                    reason = "runner_error"
                elif denial == "max_attempts_reached":
                    status = "failed_retry_exhausted"
                    reason = "max_attempts_reached"
                else:
                    status = "failed_not_retryable"
                    reason = (
                        "repair_not_needed" if denial == "repair_not_needed"
                        else "retry_not_admitted"
                    )
                return self._final(
                    status=status,
                    original_goal=goal,
                    max_attempts=self.max_attempts,
                    attempts=attempts,
                    stopped_reason=reason,
                )

        return self._final(
            status="failed_retry_exhausted",
            original_goal=goal,
            max_attempts=self.max_attempts,
            attempts=attempts,
            stopped_reason="max_attempts_reached",
        )


__all__ = [
    "RUNTIME_BOUNDED_REPAIR_RETRY_LOOP_SCHEMA",
    "RuntimeBoundedRepairRetryLoop",
]
