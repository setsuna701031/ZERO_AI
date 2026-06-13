from __future__ import annotations

"""Bridge persisted engineering goals into the engineering runtime.

EngineeringGoalRunner owns only the bridge from GoalRepository records to the
EngineeringRuntimeOrchestrator request. It does not persist goals, schedule
inside the repository, manage runtime internals, or execute task work itself.
"""

import copy
import io
import sys
import tempfile
import time
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.tasks.engineering_adaptive_planner import EngineeringAdaptivePlanner, normalize_adaptive_decision
from core.tasks.engineering_goal_dependency_graph import EngineeringGoalDependencyGraph
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_issue_summary import apply_engineering_issue_summary, build_engineering_issue_summary
from core.tasks.engineering_runtime_contract import build_engineering_runtime_contract
from core.tasks.engineering_planning_adapter import EngineeringPlanningOnlyAdapter
from core.tasks.engineering_runtime_orchestrator import EngineeringRuntimeOrchestrator


ENGINEERING_GOAL_RUNNER_SCHEMA = "zero.engineering_goal_runner.v1"
ENGINEERING_GOAL_RUNTIME_REQUEST_SCHEMA = "zero.engineering_goal_runtime_request.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _goal_id(record: Mapping[str, Any]) -> str:
    return _clean_text(record.get("goal_id") or record.get("task_id") or record.get("package_id"))


def _runtime_goal_record(goal: Mapping[str, Any]) -> dict[str, Any]:
    record = copy.deepcopy(dict(goal))
    goal_id = _goal_id(record)
    payload = copy.deepcopy(dict(record.get("payload"))) if isinstance(record.get("payload"), Mapping) else {}
    payload.setdefault("goal_id", goal_id)
    payload.setdefault("task_id", goal_id)
    payload.setdefault("package_id", goal_id)
    payload.setdefault("goal", _clean_text(record.get("summary") or record.get("goal"), goal_id))
    payload.setdefault("task_type", "engineering_task")
    record["payload"] = payload
    record.setdefault("goal_id", goal_id)
    record.setdefault("summary", _clean_text(payload.get("goal"), goal_id))
    record.setdefault("status", "pending")
    return record


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return sorted({_clean_text(item) for item in value if _clean_text(item)})


def _dependency_record_for_goal(goal: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(dict(goal.get("payload"))) if isinstance(goal.get("payload"), Mapping) else {}
    return {
        "goal_id": _goal_id(goal),
        "parent_goal_ids": _clean_list(goal.get("parent_goal_ids") or payload.get("parent_goal_ids")),
        "child_goal_ids": _clean_list(goal.get("child_goal_ids") or payload.get("child_goal_ids")),
        "prerequisite_goal_ids": _clean_list(goal.get("prerequisite_goal_ids") or payload.get("prerequisite_goal_ids")),
        "blocked_by_goal_ids": _clean_list(goal.get("blocked_by_goal_ids") or payload.get("blocked_by_goal_ids")),
    }


def _external_scheduler_override() -> Any | None:
    goal_cli = sys.modules.get("cli.goal_cli")
    factory = getattr(goal_cli, "EngineeringGoalScheduler", None)
    if not callable(factory) or getattr(factory, "__module__", "") == "core.tasks.engineering_goal_scheduler":
        return None
    try:
        return factory()
    except Exception:
        return None


class _ExternalSchedulerProxy:
    def __init__(self, scheduler: Any, goals: Sequence[Mapping[str, Any]]) -> None:
        self._scheduler = scheduler
        self._goals = [_external_scheduler_goal(goal) for goal in goals if isinstance(goal, Mapping)]

    def schedule_next_goal(self, goals: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        result = self._scheduler.schedule_next_goal(copy.deepcopy(self._goals))
        return copy.deepcopy(dict(result)) if isinstance(result, Mapping) else {}


def _external_scheduler_goal(goal: Mapping[str, Any]) -> dict[str, Any]:
    record = copy.deepcopy(dict(goal))
    for key in ("schema", "description", "metadata"):
        if key in record and not record[key]:
            record.pop(key, None)
        elif key == "schema":
            record.pop(key, None)
    payload = copy.deepcopy(dict(record.get("payload"))) if isinstance(record.get("payload"), Mapping) else {}
    for key in ("task_id", "package_id", "task_type"):
        payload.pop(key, None)
    if payload:
        record["payload"] = payload
    else:
        record.pop("payload", None)
    return record


class EngineeringGoalRunner:
    """Load persisted goals and hand them to EngineeringRuntimeOrchestrator."""

    def __init__(
        self,
        *,
        repo_root: str | Path,
        repository: EngineeringGoalRepository | Any | None = None,
        runtime_orchestrator: EngineeringRuntimeOrchestrator | Any | None = None,
        adaptive_planner: EngineeringAdaptivePlanner | Any | None = None,
        issue_reporter: Any | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.repository = repository or EngineeringGoalRepository(self.repo_root)
        self.runtime_orchestrator = runtime_orchestrator
        self.adaptive_planner = adaptive_planner or EngineeringAdaptivePlanner()
        self.issue_reporter = issue_reporter

    def run_goal(self, goal_id: str) -> dict[str, Any]:
        target_goal_id = _clean_text(goal_id)
        goal = self.repository.load_goal(target_goal_id)
        if goal is None:
            return self._not_found_result(target_goal_id)
        request = self.build_runtime_request([goal], selected_goal_id=target_goal_id)
        runtime_result, runtime_stdout = self._run_runtime(request, scheduler_goals=[goal])
        runtime_root_cause = self._runtime_root_cause(runtime_result) if not bool(runtime_result.get("ok")) else {}
        issue_summary = build_engineering_issue_summary(self.repo_root, issue_reporter=self.issue_reporter)
        adaptive_decision = self.adaptive_planner.decide_next_action(
            goal=goal,
            runtime_result=runtime_result,
            runtime_root_cause=runtime_root_cause,
            issue_summary=issue_summary,
        )
        return self._runner_result(
            ok=bool(runtime_result.get("ok")),
            action="run_goal",
            goal_id=target_goal_id,
            runtime_request=request,
            runtime_result=runtime_result,
            runtime_stdout=runtime_stdout,
            runtime_root_cause=runtime_root_cause,
            adaptive_decision=adaptive_decision,
            issue_summary=issue_summary,
        )

    def run_next_goal(self) -> dict[str, Any]:
        goals = self.repository.list_goals()
        request = self.build_runtime_request(goals)
        runtime_result, runtime_stdout = self._run_runtime(request, scheduler_goals=goals)
        selected_goal_id = _clean_text(
            (
                copy.deepcopy(runtime_result.get("iterations", [{}])[0])
                if isinstance(runtime_result, Mapping) and runtime_result.get("iterations")
                else {}
            ).get("goal_id")
        )
        selected_goal = self._goal_for_adaptive_decision(goals, selected_goal_id)
        runtime_root_cause = self._runtime_root_cause(runtime_result) if not bool(runtime_result.get("ok")) else {}
        issue_summary = build_engineering_issue_summary(self.repo_root, issue_reporter=self.issue_reporter)
        adaptive_decision = self.adaptive_planner.decide_next_action(
            goal=selected_goal,
            runtime_result=runtime_result,
            runtime_root_cause=runtime_root_cause,
            issue_summary=issue_summary,
        )
        return self._runner_result(
            ok=bool(runtime_result.get("ok")),
            action="run_next_goal",
            goal_id=selected_goal_id,
            runtime_request=request,
            runtime_result=runtime_result,
            runtime_stdout=runtime_stdout,
            runtime_root_cause=runtime_root_cause,
            adaptive_decision=adaptive_decision,
            issue_summary=issue_summary,
        )

    def build_runtime_request(
        self,
        goals: Sequence[Mapping[str, Any]],
        *,
        selected_goal_id: str = "",
    ) -> dict[str, Any]:
        records = [_runtime_goal_record(goal) for goal in goals if isinstance(goal, Mapping)]
        return {
            "schema": ENGINEERING_GOAL_RUNTIME_REQUEST_SCHEMA,
            "mode": "engineering_goal_runtime_bridge",
            "selected_goal_id": _clean_text(selected_goal_id),
            "goals": records,
            "dependency_records": [_dependency_record_for_goal(goal) for goal in records],
            "runtime_entrypoint": "core.tasks.engineering_runtime_orchestrator.EngineeringRuntimeOrchestrator.run",
            "execution_path": {
                "repository_persists_only": True,
                "goal_runner_bridges_only": True,
                "runtime_orchestrator_owns_runtime_loop": True,
                "legacy_isolated": True,
                "work_package_mainline": False,
                "work_package_execution_authority": False,
                "goal_repository_in_orchestrator": False,
                "direct_execution": False,
                "runtime_owns_execution": True,
                "taskrunner_required": True,
                "step_executor_endpoint_only": True,
                "new_execution_path": False,
            },
            "created_at": time.time(),
        }

    def _not_found_result(self, goal_id: str) -> dict[str, Any]:
        return apply_engineering_issue_summary(
            {
            "schema": ENGINEERING_GOAL_RUNNER_SCHEMA,
            "ok": False,
            "mode": "engineering_goal_runner",
            "action": "run_goal",
            "goal_id": goal_id,
            "error": "engineering_goal_not_found",
            "runtime_request": {},
            "runtime_result": {},
            "runtime_stdout": "",
            "runtime_root_cause": {"reason": "engineering_goal_not_found"},
            "adaptive_decision": normalize_adaptive_decision({
                "decision": "blocked",
                "reason": "engineering_goal_not_found",
                "confidence": 1.0,
                "next_action": "stop_with_root_cause",
                "continuation_plan": {},
                "replan_request": {},
                "blocking_issues": [],
                "root_cause": {"reason": "engineering_goal_not_found"},
            }),
            "execution_path": {
                "repository_persists_only": True,
                "goal_runner_bridges_only": True,
                "runtime_orchestrator_owns_runtime_loop": False,
                "legacy_isolated": True,
                "work_package_mainline": False,
                "work_package_execution_authority": False,
                "direct_execution": False,
                "runtime_owns_execution": False,
                "taskrunner_required": True,
                "step_executor_endpoint_only": True,
            },
            },
            repo_root=self.repo_root,
            issue_reporter=self.issue_reporter,
        )

    def _run_runtime(
        self,
        request: Mapping[str, Any],
        *,
        scheduler_goals: Sequence[Mapping[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], str]:
        stream = io.StringIO()
        goals = request.get("goals") if isinstance(request.get("goals"), list) else []
        dependency_records = request.get("dependency_records") if isinstance(request.get("dependency_records"), list) else []
        with redirect_stdout(stream):
            if self.runtime_orchestrator is not None:
                orchestrator = self.runtime_orchestrator
                result = orchestrator.run(goals)
            else:
                with tempfile.TemporaryDirectory(prefix="zero_goal_runtime_") as runtime_dir:
                    runtime_root = Path(runtime_dir)
                    scheduler_override = _external_scheduler_override()
                    orchestrator = EngineeringRuntimeOrchestrator(
                        repo_root=runtime_root,
                        scheduler=_ExternalSchedulerProxy(scheduler_override, scheduler_goals or goals)
                        if scheduler_override is not None
                        else None,
                        dependency_graph=EngineeringGoalDependencyGraph(dependency_records),
                        planning_loop=EngineeringPlanningOnlyAdapter(repo_root=runtime_root),
                    )
                    result = orchestrator.run(goals)
        return copy.deepcopy(dict(result)) if isinstance(result, Mapping) else {}, stream.getvalue()

    def _goal_for_adaptive_decision(self, goals: Sequence[Mapping[str, Any]], selected_goal_id: str) -> dict[str, Any]:
        target = _clean_text(selected_goal_id)
        for goal in goals:
            if isinstance(goal, Mapping) and _goal_id(goal) == target:
                return copy.deepcopy(dict(goal))
        return copy.deepcopy(dict(goals[0])) if goals and isinstance(goals[0], Mapping) else {"goal_id": target}

    def _runner_result(
        self,
        *,
        ok: bool,
        action: str,
        goal_id: str,
        runtime_request: Mapping[str, Any],
        runtime_result: Mapping[str, Any],
        runtime_stdout: str,
        runtime_root_cause: Mapping[str, Any],
        adaptive_decision: Mapping[str, Any],
        issue_summary: Mapping[str, Any],
    ) -> dict[str, Any]:
        runtime_contract = build_engineering_runtime_contract(
            goal_id=goal_id,
            action=action,
            ok=bool(ok),
            runtime_request=runtime_request,
            runtime_result=runtime_result,
            runtime_stdout=runtime_stdout,
            runtime_root_cause=runtime_root_cause,
            adaptive_decision=adaptive_decision,
            issue_summary=issue_summary,
        )
        return apply_engineering_issue_summary(
            {
            "schema": ENGINEERING_GOAL_RUNNER_SCHEMA,
            "ok": bool(ok),
            "mode": "engineering_goal_runner",
            "action": action,
            "goal_id": goal_id,
            "engineering_runtime_contract": runtime_contract,
            "runtime_request": copy.deepcopy(dict(runtime_request)),
            "runtime_result": copy.deepcopy(dict(runtime_result)) if isinstance(runtime_result, Mapping) else {},
            "runtime_stdout": str(runtime_stdout or ""),
            "runtime_root_cause": copy.deepcopy(dict(runtime_root_cause)),
            "adaptive_decision": copy.deepcopy(dict(adaptive_decision)),
            "execution_path": {
                "repository_persists_only": True,
                "goal_runner_bridges_only": True,
                "runner_produces_runtime_contract": True,
                "runtime_orchestrator_owns_runtime_loop": True,
                "legacy_isolated": True,
                "work_package_mainline": False,
                "work_package_execution_authority": False,
                "adaptive_planner_after_runtime": True,
                "goal_repository_in_orchestrator": False,
                "direct_execution": False,
                "runtime_owns_execution": True,
                "taskrunner_required": True,
                "step_executor_endpoint_only": True,
                "new_execution_path": False,
            },
            "updated_at": time.time(),
            },
            repo_root=self.repo_root,
            issue_reporter=self.issue_reporter,
            issue_summary=issue_summary,
        )

    def _runtime_root_cause(self, runtime_result: Mapping[str, Any]) -> dict[str, Any]:
        iterations = runtime_result.get("iterations") if isinstance(runtime_result.get("iterations"), list) else []
        latest = copy.deepcopy(iterations[-1]) if iterations and isinstance(iterations[-1], Mapping) else {}
        continuation = latest.get("continuation_result") if isinstance(latest.get("continuation_result"), Mapping) else {}
        lifecycle = (
            continuation.get("goal_lifecycle")
            if isinstance(continuation.get("goal_lifecycle"), Mapping)
            else latest.get("lifecycle_result", {}).get("goal_lifecycle")
            if isinstance(latest.get("lifecycle_result"), Mapping)
            and isinstance(latest.get("lifecycle_result", {}).get("goal_lifecycle"), Mapping)
            else {}
        )
        latest_result = continuation.get("latest_result") if isinstance(continuation.get("latest_result"), Mapping) else {}
        result_bundle = latest_result.get("result_bundle") if isinstance(latest_result.get("result_bundle"), Mapping) else {}
        observations = result_bundle.get("observations") if isinstance(result_bundle.get("observations"), list) else []
        latest_observation = copy.deepcopy(observations[-1]) if observations and isinstance(observations[-1], Mapping) else {}
        return {
            "state": _clean_text(runtime_result.get("state")),
            "stop_reason": _clean_text(runtime_result.get("stop_reason")),
            "decision_state": _clean_text(runtime_result.get("decision_state")),
            "goal_state": _clean_text(lifecycle.get("goal_state")) if isinstance(lifecycle, Mapping) else "",
            "failed_tasks": copy.deepcopy(lifecycle.get("failed_tasks")) if isinstance(lifecycle, Mapping) and isinstance(lifecycle.get("failed_tasks"), list) else [],
            "blocked_tasks": copy.deepcopy(lifecycle.get("blocked_tasks")) if isinstance(lifecycle, Mapping) and isinstance(lifecycle.get("blocked_tasks"), list) else [],
            "latest_observation": latest_observation,
        }


__all__ = [
    "ENGINEERING_GOAL_RUNNER_SCHEMA",
    "ENGINEERING_GOAL_RUNTIME_REQUEST_SCHEMA",
    "EngineeringGoalRunner",
]
