from __future__ import annotations

"""Runtime orchestration for the engineering goal stack.

EngineeringRuntimeOrchestrator owns only the runtime loop. It asks the
existing owner components to schedule, validate dependencies, plan, continue,
evaluate, and persist evaluator decisions. It does not generate plans, mutate
lifecycle files, execute tasks, or persist memory itself.
"""

import copy
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from core.tasks.adaptive_planning_evaluator import AdaptivePlanningEvaluator
from core.tasks.engineering_goal_dependency_graph import EngineeringGoalDependencyGraph
from core.tasks.engineering_goal_lifecycle import EngineeringGoalLifecycle
from core.tasks.engineering_goal_scheduler import EngineeringGoalScheduler
from core.tasks.engineering_planning_loop import EngineeringPlanningLoop
from core.tasks.goal_continuation_coordinator import GoalContinuationCoordinator


ENGINEERING_RUNTIME_ORCHESTRATOR_SCHEMA = "zero.engineering_runtime_orchestrator.v1"
RUNTIME_TRACE_EVENT_SCHEMA = "zero.engineering_runtime_orchestrator.trace_event.v1"
RUNTIME_DECISION_STATES = {"running", "replan", "blocked", "complete", "cancelled", "idle"}
TERMINAL_RUNTIME_STATES = {"blocked", "complete", "cancelled", "idle"}


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _goal_id(record: Mapping[str, Any]) -> str:
    return _clean_text(record.get("goal_id") or record.get("task_id") or record.get("package_id"))


def _goal_statuses(goals: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    return {
        _goal_id(goal): _clean_text(goal.get("status"), "pending").lower()
        for goal in goals
        if _goal_id(goal)
    }


def _payload_for_goal(goal: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(_as_mapping(goal.get("payload") or goal.get("planning_payload")))
    goal_id = _goal_id(goal)
    payload.setdefault("goal_id", goal_id)
    payload.setdefault("task_id", goal_id)
    payload.setdefault("package_id", goal_id)
    payload.setdefault("task_type", "engineering_task")
    payload.setdefault("engineering_goal_lifecycle", True)
    if "goal" not in payload:
        payload["goal"] = _clean_text(goal.get("summary") or goal.get("goal"), goal_id)
    return payload


def _trace_event(event: str, state: str, **fields: Any) -> dict[str, Any]:
    return {
        "schema": RUNTIME_TRACE_EVENT_SCHEMA,
        "event": event,
        "state": state,
        "created_at": time.time(),
        **copy.deepcopy(fields),
    }


class _LifecycleDecisionApplier:
    def __init__(
        self,
        *,
        repo_root: Path,
        lifecycle_owner: type[EngineeringGoalLifecycle] | Any,
    ) -> None:
        self.repo_root = repo_root
        self.lifecycle_owner = lifecycle_owner

    def apply_evaluator_decision(
        self,
        *,
        payload: Mapping[str, Any],
        planning_result: Mapping[str, Any],
        continuation_result: Mapping[str, Any],
        evaluator_decision: Mapping[str, Any],
    ) -> dict[str, Any]:
        state = (
            _as_mapping(continuation_result.get("goal_lifecycle"))
            or _as_mapping(planning_result.get("goal_lifecycle"))
            or _as_mapping(planning_result.get("engineering_goal_lifecycle"))
        )
        if not state:
            return {
                "ok": False,
                "delegated": False,
                "owner": "core.tasks.engineering_goal_lifecycle.EngineeringGoalLifecycle",
                "reason": "lifecycle_state_unavailable",
                "decision": copy.deepcopy(dict(evaluator_decision)),
                "payload_goal_id": _clean_text(payload.get("goal_id")),
            }

        lifecycle = self.lifecycle_owner(
            repo_root=self.repo_root,
            payload=payload,
            plan=self._plan_for_lifecycle(payload, planning_result),
            raw_steps=self._raw_steps_for_lifecycle(payload, planning_result),
        )
        decision = _clean_text(evaluator_decision.get("decision")).lower()
        if decision in {"block", "complete"}:
            updated_state = lifecycle.apply_adaptive_terminal_decision(
                state=state,
                decision=evaluator_decision,
            )
        else:
            updated_state = lifecycle.record_adaptive_decision(
                state=state,
                decision=evaluator_decision,
            )
        return {
            "ok": True,
            "delegated": True,
            "owner": "core.tasks.engineering_goal_lifecycle.EngineeringGoalLifecycle",
            "decision": copy.deepcopy(dict(evaluator_decision)),
            "goal_lifecycle": copy.deepcopy(updated_state),
            "payload_goal_id": _clean_text(payload.get("goal_id")),
        }

    def _plan_for_lifecycle(
        self,
        payload: Mapping[str, Any],
        planning_result: Mapping[str, Any],
    ) -> dict[str, Any]:
        for event in _as_list(planning_result.get("planning_events")):
            if not isinstance(event, Mapping):
                continue
            plan = _as_mapping(event.get("multi_step_plan"))
            if plan:
                return plan
        return {
            "package_id": _clean_text(payload.get("package_id") or payload.get("task_id")),
            "goal": _clean_text(payload.get("goal")),
        }

    def _raw_steps_for_lifecycle(
        self,
        payload: Mapping[str, Any],
        planning_result: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        for event in _as_list(planning_result.get("planning_events")):
            if not isinstance(event, Mapping):
                continue
            steps = [copy.deepcopy(dict(item)) for item in _as_list(event.get("steps")) if isinstance(item, Mapping)]
            if steps:
                return steps
        return [copy.deepcopy(dict(item)) for item in _as_list(payload.get("steps")) if isinstance(item, Mapping)]


class EngineeringRuntimeOrchestrator:
    """Coordinate the sealed engineering owners without taking their work."""

    def __init__(
        self,
        *,
        repo_root: str | Path,
        scheduler: EngineeringGoalScheduler | Any | None = None,
        dependency_graph: EngineeringGoalDependencyGraph | Any | None = None,
        planning_loop: EngineeringPlanningLoop | Any | None = None,
        evaluator: AdaptivePlanningEvaluator | Any | None = None,
        continuation_coordinator: GoalContinuationCoordinator | Any | None = None,
        lifecycle_decision_applier: Any | None = None,
        lifecycle_owner: type[EngineeringGoalLifecycle] | Any = EngineeringGoalLifecycle,
        max_iterations: int = 10,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.scheduler = scheduler or EngineeringGoalScheduler()
        self.dependency_graph = dependency_graph or EngineeringGoalDependencyGraph()
        self.planning_loop = planning_loop or EngineeringPlanningLoop(repo_root=self.repo_root)
        self.evaluator = evaluator or AdaptivePlanningEvaluator()
        self.continuation_coordinator = continuation_coordinator or GoalContinuationCoordinator(repo_root=self.repo_root)
        self.lifecycle_owner = lifecycle_owner
        self.lifecycle_decision_applier = lifecycle_decision_applier or _LifecycleDecisionApplier(
            repo_root=self.repo_root,
            lifecycle_owner=self.lifecycle_owner,
        )
        self.max_iterations = max(1, int(max_iterations or 1))

    def run(self, goals: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        records = [copy.deepcopy(dict(goal)) for goal in goals if isinstance(goal, Mapping)]
        trace: list[dict[str, Any]] = []
        iterations: list[dict[str, Any]] = []
        final_state = "idle"
        stop_reason = "no_runnable_goals"

        for iteration in range(1, self.max_iterations + 1):
            scheduler_result = self._schedule_next(records)
            scheduler_decision = _as_mapping(scheduler_result.get("scheduler_decision"))
            selected_goal_id = _clean_text(scheduler_decision.get("selected_goal_id"))
            trace.append(
                _trace_event(
                    "scheduler_selected_goal" if selected_goal_id else "scheduler_idle",
                    "running" if selected_goal_id else "idle",
                    iteration=iteration,
                    scheduler_decision=scheduler_decision,
                )
            )

            if not selected_goal_id:
                final_state = "idle"
                stop_reason = "no_runnable_goals"
                iterations.append(
                    {
                        "iteration": iteration,
                        "state": final_state,
                        "scheduler_result": copy.deepcopy(scheduler_result),
                    }
                )
                break

            selected_goal = self._find_goal(records, selected_goal_id)
            dependency_status = self.dependency_graph.prerequisite_status(
                selected_goal_id,
                _goal_statuses(records),
            )
            dependency_graph_status = self.dependency_graph.as_dict(_goal_statuses(records))
            dependency_ready = bool(dependency_status.get("ready"))
            trace.append(
                _trace_event(
                    "dependencies_validated",
                    "running" if dependency_ready else "blocked",
                    iteration=iteration,
                    goal_id=selected_goal_id,
                    dependency_status=dependency_status,
                )
            )
            if not dependency_ready:
                final_state = "blocked"
                stop_reason = _clean_text(dependency_status.get("reason"), "dependencies_unsatisfied")
                iterations.append(
                    {
                        "iteration": iteration,
                        "state": final_state,
                        "goal_id": selected_goal_id,
                        "scheduler_result": copy.deepcopy(scheduler_result),
                        "dependency_status": copy.deepcopy(dependency_status),
                        "dependency_graph": copy.deepcopy(dependency_graph_status),
                    }
                )
                break

            payload = _payload_for_goal(selected_goal)
            planning_result = self.planning_loop.run(copy.deepcopy(payload))
            trace.append(
                _trace_event(
                    "planning_loop_invoked",
                    "running",
                    iteration=iteration,
                    goal_id=selected_goal_id,
                    planning_result_summary=self._planning_summary(planning_result),
                )
            )
            continuation_result = self.continuation_coordinator.continue_goal(copy.deepcopy(payload))
            trace.append(
                _trace_event(
                    "continuation_invoked",
                    "running",
                    iteration=iteration,
                    goal_id=selected_goal_id,
                    continuation_summary=self._continuation_summary(continuation_result),
                )
            )
            evaluator_decision = self.evaluator.evaluate(
                latest_execution_result=continuation_result,
                current_goal_state=self._current_goal_state(planning_result, continuation_result),
                current_task_buckets=self._current_task_buckets(planning_result, continuation_result),
                memory_summary=_as_mapping(planning_result.get("memory")),
            )
            decision_state = self._decision_state(evaluator_decision, planning_result, continuation_result)
            trace.append(
                _trace_event(
                    "evaluator_decision",
                    decision_state,
                    iteration=iteration,
                    goal_id=selected_goal_id,
                    evaluator_decision=evaluator_decision,
                )
            )
            lifecycle_result = self.lifecycle_decision_applier.apply_evaluator_decision(
                payload=payload,
                planning_result=planning_result,
                continuation_result=continuation_result,
                evaluator_decision=evaluator_decision,
            )
            trace.append(
                _trace_event(
                    "lifecycle_decision_applied",
                    decision_state,
                    iteration=iteration,
                    goal_id=selected_goal_id,
                    lifecycle_result=lifecycle_result,
                    lifecycle_owner=getattr(self.lifecycle_owner, "__name__", str(self.lifecycle_owner)),
                )
            )
            iterations.append(
                {
                    "iteration": iteration,
                    "state": decision_state,
                    "goal_id": selected_goal_id,
                    "scheduler_result": copy.deepcopy(scheduler_result),
                    "dependency_status": copy.deepcopy(dependency_status),
                    "dependency_graph": copy.deepcopy(dependency_graph_status),
                    "planning_result": copy.deepcopy(dict(planning_result)) if isinstance(planning_result, Mapping) else {},
                    "continuation_result": copy.deepcopy(dict(continuation_result))
                    if isinstance(continuation_result, Mapping)
                    else {},
                    "evaluator_decision": copy.deepcopy(dict(evaluator_decision))
                    if isinstance(evaluator_decision, Mapping)
                    else {},
                    "lifecycle_result": copy.deepcopy(dict(lifecycle_result)) if isinstance(lifecycle_result, Mapping) else {},
                }
            )

            if decision_state in TERMINAL_RUNTIME_STATES:
                final_state = decision_state
                stop_reason = decision_state
                break

            if decision_state == "replan":
                final_state = "replan"
                stop_reason = "evaluator_requested_replan"
                continue

            final_state = "running"
            stop_reason = "iteration_limit_reached"

        return {
            "schema": ENGINEERING_RUNTIME_ORCHESTRATOR_SCHEMA,
            "ok": final_state == "complete",
            "mode": "engineering_runtime_orchestrator",
            "state": final_state,
            "decision_state": final_state,
            "terminal": final_state in TERMINAL_RUNTIME_STATES,
            "stop_reason": stop_reason,
            "iterations": iterations,
            "runtime_trace": trace,
            "execution_path": {
                "orchestrator_owns_runtime_loop_only": True,
                "scheduler_schedules_only": True,
                "dependency_graph_validates_only": True,
                "planning_loop_owns_planning": True,
                "continuation_coordinator_delegates_execution": True,
                "adaptive_evaluator_decides_only": True,
                "lifecycle_owner_applies_state": True,
                "direct_execution": False,
                "runtime_owns_execution": True,
                "taskrunner_required": True,
                "step_executor_endpoint_only": True,
                "new_execution_path": False,
                "memory_persistence_owned_here": False,
            },
            "updated_at": time.time(),
        }

    def _schedule_next(self, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        if hasattr(self.scheduler, "schedule_next_goal"):
            result = self.scheduler.schedule_next_goal(records)
        else:
            result = self.scheduler.run_next_goal(records, planning_loop=_PlanningLoopNotAvailable())
        return copy.deepcopy(dict(result)) if isinstance(result, Mapping) else {}

    def _find_goal(self, records: Sequence[Mapping[str, Any]], goal_id: str) -> dict[str, Any]:
        for record in records:
            if _goal_id(record) == goal_id:
                return copy.deepcopy(dict(record))
        return {"goal_id": goal_id, "status": "pending", "payload": {"goal_id": goal_id}}

    def _decision_state(
        self,
        evaluator_decision: Mapping[str, Any],
        planning_result: Mapping[str, Any],
        continuation_result: Mapping[str, Any],
    ) -> str:
        lifecycle = self._current_goal_state(planning_result, continuation_result)
        goal_state = _clean_text(lifecycle.get("goal_state")).lower()
        if goal_state == "cancelled":
            return "cancelled"
        if goal_state == "completed":
            return "complete"
        decision = _clean_text(evaluator_decision.get("decision")).lower()
        if decision == "complete":
            return "complete"
        if decision == "block":
            return "blocked"
        if decision == "replan":
            return "replan"
        return "running"

    def _current_goal_state(
        self,
        planning_result: Mapping[str, Any],
        continuation_result: Mapping[str, Any],
    ) -> dict[str, Any]:
        return (
            _as_mapping(continuation_result.get("goal_lifecycle"))
            or _as_mapping(continuation_result.get("engineering_goal_lifecycle"))
            or _as_mapping(planning_result.get("goal_lifecycle"))
            or _as_mapping(planning_result.get("engineering_goal_lifecycle"))
        )

    def _current_task_buckets(
        self,
        planning_result: Mapping[str, Any],
        continuation_result: Mapping[str, Any],
    ) -> dict[str, Any]:
        lifecycle = self._current_goal_state(planning_result, continuation_result)
        return _as_mapping(lifecycle.get("task_buckets")) or _as_mapping(planning_result.get("task_buckets"))

    def _planning_summary(self, planning_result: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "ok": bool(planning_result.get("ok")),
            "goal_id": _clean_text(planning_result.get("goal_id")),
            "goal_state": _clean_text(planning_result.get("goal_state")),
            "replan_count": len(_as_list(planning_result.get("replans"))),
        }

    def _continuation_summary(self, continuation_result: Mapping[str, Any]) -> dict[str, Any]:
        lifecycle = _as_mapping(continuation_result.get("goal_lifecycle"))
        return {
            "ok": bool(continuation_result.get("ok")),
            "terminal": bool(continuation_result.get("terminal")),
            "stopped_reason": _clean_text(continuation_result.get("stopped_reason")),
            "goal_state": _clean_text(lifecycle.get("goal_state")),
        }


class _PlanningLoopNotAvailable:
    def run(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "ok": False,
            "payload": copy.deepcopy(dict(payload)),
            "error": "planning_loop_not_available_for_scheduler_fallback",
        }


def run_engineering_runtime(
    goals: Sequence[Mapping[str, Any]],
    *,
    repo_root: str | Path,
    max_iterations: int = 10,
) -> dict[str, Any]:
    return EngineeringRuntimeOrchestrator(repo_root=repo_root, max_iterations=max_iterations).run(goals)


__all__ = [
    "ENGINEERING_RUNTIME_ORCHESTRATOR_SCHEMA",
    "RUNTIME_DECISION_STATES",
    "RUNTIME_TRACE_EVENT_SCHEMA",
    "EngineeringRuntimeOrchestrator",
    "run_engineering_runtime",
]
