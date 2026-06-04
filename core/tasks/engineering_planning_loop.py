from __future__ import annotations

"""Engineering planning loop orchestration.

This loop plans task buckets, persists them through EngineeringGoalLifecycle,
delegates execution orchestration to GoalContinuationCoordinator, reads memory,
and optionally replans. It does not execute work packages itself.
"""

import copy
import time
from pathlib import Path
from typing import Any, Mapping

from core.planning.planner import Planner
from core.tasks.adaptive_planning_evaluator import AdaptivePlanningEvaluator
from core.tasks.engineering_goal_lifecycle import EngineeringGoalLifecycle
from core.tasks.engineering_memory_store import EngineeringMemoryStore
from core.tasks.engineering_task_runner import build_multi_step_plan, decompose_engineering_goal
from core.tasks.goal_continuation_coordinator import GoalContinuationCoordinator


ENGINEERING_PLANNING_LOOP_SCHEMA = "zero.engineering_planning_loop.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _task_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    package = payload.get("package")
    if isinstance(package, Mapping):
        return dict(package)
    return dict(payload)


def _extract_bucket_steps(planner_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    buckets = planner_result.get("task_buckets")
    if isinstance(buckets, Mapping):
        pending = buckets.get("pending")
        if isinstance(pending, list):
            steps: list[dict[str, Any]] = []
            for item in pending:
                if isinstance(item, Mapping) and isinstance(item.get("task_payload"), Mapping):
                    steps.append(copy.deepcopy(dict(item["task_payload"])))
                elif isinstance(item, Mapping):
                    steps.append(copy.deepcopy(dict(item)))
            if steps:
                return steps

    for key in ("engineering_steps", "task_steps", "steps"):
        raw_steps = planner_result.get(key)
        if isinstance(raw_steps, list):
            steps = [copy.deepcopy(dict(item)) for item in raw_steps if isinstance(item, Mapping)]
            if any(isinstance(step.get("edits"), list) or isinstance(step.get("edit"), Mapping) for step in steps):
                return steps
    return []


class EngineeringPlanningLoop:
    """Plan, persist, continue, read memory, and replan engineering goals."""

    def __init__(
        self,
        *,
        repo_root: str | Path,
        planner: Any | None = None,
        continuation_coordinator: GoalContinuationCoordinator | Any | None = None,
        memory_store: EngineeringMemoryStore | Any | None = None,
        adaptive_evaluator: AdaptivePlanningEvaluator | Any | None = None,
        max_replans: int = 2,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.planner = planner or Planner()
        self.memory_store = memory_store or EngineeringMemoryStore(self.repo_root)
        self.continuation_coordinator = continuation_coordinator or GoalContinuationCoordinator(repo_root=self.repo_root)
        self.adaptive_evaluator = adaptive_evaluator or AdaptivePlanningEvaluator()
        self.max_replans = max(0, int(max_replans or 0))

    def run(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise ValueError("engineering_planning_loop_payload_must_be_mapping")

        base_payload = copy.deepcopy(dict(payload))
        task = _task_payload(base_payload)
        goal = _clean_text(task.get("goal") or base_payload.get("goal"), _clean_text(task.get("task_id"), "engineering_goal"))
        package_id = _clean_text(task.get("package_id") or task.get("task_id") or base_payload.get("task_id"), "engineering_goal")
        base_payload.update(
            {
                "task_type": _clean_text(base_payload.get("task_type"), "engineering_task"),
                "engineering_goal_lifecycle": True,
                "goal_id": _clean_text(task.get("goal_id") or base_payload.get("goal_id"), package_id),
                "task_id": package_id,
                "package_id": package_id,
                "goal": goal,
                "mode": _clean_text(task.get("mode") or base_payload.get("mode"), "execute"),
                "approval": bool(task.get("approval") if "approval" in task else base_payload.get("approval", True)),
            }
        )

        planning_events: list[dict[str, Any]] = []
        replans: list[dict[str, Any]] = []
        latest_continuation: dict[str, Any] = {}
        latest_lifecycle: dict[str, Any] = {}
        latest_memory: dict[str, Any] = {}
        adaptive_decisions: list[dict[str, Any]] = []
        current_payload = copy.deepcopy(base_payload)

        initial_plan = self._plan_payload(
            current_payload,
            reason="initial_plan",
            lifecycle_state={},
            latest_result={},
            relevant_memory={},
        )
        current_payload["steps"] = copy.deepcopy(initial_plan["steps"])
        current_payload["planned_task_buckets"] = copy.deepcopy(initial_plan["task_buckets"])
        latest_lifecycle = self._persist_initial_lifecycle(current_payload, initial_plan)
        planning_events.append(initial_plan)

        for round_index in range(0, self.max_replans + 1):
            latest_continuation = self.continuation_coordinator.continue_goal(current_payload)
            latest_lifecycle = _as_mapping(latest_continuation.get("goal_lifecycle"))
            if adaptive_decisions and not isinstance(latest_lifecycle.get("adaptive_planning_decisions"), list):
                latest_lifecycle["adaptive_planning_decisions"] = copy.deepcopy(adaptive_decisions)
            latest_memory = self.memory_store.load_relevant_memory(goal=goal)
            lifecycle = self._lifecycle_for_payload(current_payload)
            adaptive_decision = self.adaptive_evaluator.evaluate(
                latest_execution_result=latest_continuation,
                current_goal_state=latest_lifecycle,
                current_task_buckets=_as_mapping(latest_lifecycle.get("task_buckets")),
                memory_summary=latest_memory,
            )
            adaptive_decisions.append(copy.deepcopy(adaptive_decision))

            if adaptive_decision.get("decision") in {"block", "complete"}:
                latest_lifecycle = lifecycle.apply_adaptive_terminal_decision(
                    state=latest_lifecycle,
                    decision=adaptive_decision,
                )
                break

            latest_lifecycle = lifecycle.record_adaptive_decision(
                state=latest_lifecycle,
                decision=adaptive_decision,
            )

            if adaptive_decision.get("decision") != "replan":
                break
            replan_reason = _clean_text(adaptive_decision.get("reason"), "adaptive_planning_replan")
            if round_index >= self.max_replans:
                break

            replan = self._plan_payload(
                current_payload,
                reason=replan_reason,
                lifecycle_state=latest_lifecycle,
                latest_result=latest_continuation,
                relevant_memory=latest_memory,
                replan_index=len(replans) + 1,
            )
            if not replan["steps"]:
                break
            lifecycle = self._lifecycle_for_payload(current_payload)
            latest_lifecycle = lifecycle.append_planned_tasks(
                state=latest_lifecycle,
                new_steps=replan["steps"],
                reason=replan_reason,
                supersede_task_ids=[str(item) for item in latest_lifecycle.get("blocked_tasks", []) if str(item).strip()],
            )
            current_payload["steps"] = [
                *[copy.deepcopy(dict(item)) for item in current_payload.get("steps", []) if isinstance(item, Mapping)],
                *copy.deepcopy(replan["steps"]),
            ]
            current_payload["planned_task_buckets"] = copy.deepcopy(latest_lifecycle.get("task_buckets", {}))
            replan["persisted_lifecycle"] = copy.deepcopy(latest_lifecycle)
            planning_events.append(replan)
            replans.append(replan)

        final_state = _clean_text(latest_lifecycle.get("goal_state")).lower()
        return {
            "schema": ENGINEERING_PLANNING_LOOP_SCHEMA,
            "ok": final_state == "completed",
            "mode": "engineering_planning_loop",
            "goal_id": _clean_text(latest_lifecycle.get("goal_id") or current_payload.get("goal_id")),
            "goal_state": final_state,
            "terminal": final_state in {"completed", "blocked", "failed", "cancelled"},
            "planning_events": planning_events,
            "task_buckets": copy.deepcopy(latest_lifecycle.get("task_buckets", initial_plan["task_buckets"])),
            "goal_lifecycle": latest_lifecycle,
            "engineering_goal_lifecycle": copy.deepcopy(latest_lifecycle),
            "continuation_result": latest_continuation,
            "memory": latest_memory,
            "adaptive_planning_decisions": adaptive_decisions,
            "latest_adaptive_planning_decision": copy.deepcopy(adaptive_decisions[-1]) if adaptive_decisions else {},
            "replans": replans,
            "replan_count": len(replans),
            "execution_path": {
                "orchestrates_only": True,
                "direct_execution": False,
                "sequence": "Planner -> GoalLifecycle -> GoalContinuationCoordinator -> AdaptivePlanningEvaluator -> EngineeringMemoryStore",
                "continuation_coordinator_executes": True,
                "adaptive_evaluator_decides_only": True,
                "existing_aer_path_reused": True,
                "new_execution_path": False,
            },
            "updated_at": time.time(),
        }

    def _plan_payload(
        self,
        payload: Mapping[str, Any],
        *,
        reason: str,
        lifecycle_state: Mapping[str, Any],
        latest_result: Mapping[str, Any],
        relevant_memory: Mapping[str, Any],
        replan_index: int = 0,
    ) -> dict[str, Any]:
        task = _task_payload(payload)
        goal = _clean_text(task.get("goal") or payload.get("goal"), _clean_text(task.get("task_id"), "engineering_goal"))
        planner_result = self.planner.plan(
            context={
                "engineering_goal_payload": copy.deepcopy(dict(payload)),
                "engineering_goal_lifecycle": copy.deepcopy(dict(lifecycle_state)),
                "engineering_memory": copy.deepcopy(dict(relevant_memory)),
                "latest_continuation_result": copy.deepcopy(dict(latest_result)),
                "planning_reason": reason,
                "replan_index": replan_index,
            },
            user_input=goal,
            route={"mode": "engineering_goal_planning", "reason": reason},
        )
        planner_result = planner_result if isinstance(planner_result, Mapping) else {}
        steps = _extract_bucket_steps(planner_result)
        if not steps:
            if isinstance(task.get("steps"), list) and reason == "initial_plan":
                steps = [copy.deepcopy(dict(item)) for item in task["steps"] if isinstance(item, Mapping)]
            elif reason == "initial_plan":
                steps = [
                    copy.deepcopy(dict(item))
                    for item in decompose_engineering_goal(payload).get("steps", [])
                    if isinstance(item, Mapping)
                ]

        planned_payload = copy.deepcopy(dict(payload))
        planned_payload["steps"] = copy.deepcopy(steps)
        multi_step_plan = build_multi_step_plan(planned_payload)
        task_buckets = {
            "pending": [
                {
                    "summary": {
                        "task_id": _clean_text(step.get("package_id") or step.get("task_id"), f"planned_task_{index}"),
                        "goal": _clean_text(step.get("goal") or step.get("title"), f"planned_task_{index}"),
                        "step_index": index,
                    },
                    "task_payload": copy.deepcopy(step),
                }
                for index, step in enumerate(steps, start=1)
            ],
            "running": [],
            "completed": [],
            "blocked": [],
            "failed": [],
            "cancelled": [],
        }
        return {
            "schema": "zero.engineering_planning_loop.plan_event.v1",
            "reason": reason,
            "replan_index": replan_index,
            "planner_result": copy.deepcopy(dict(planner_result)),
            "planner_called": True,
            "steps": steps,
            "task_buckets": task_buckets,
            "multi_step_plan": multi_step_plan,
        }

    def _persist_initial_lifecycle(self, payload: Mapping[str, Any], plan_event: Mapping[str, Any]) -> dict[str, Any]:
        lifecycle = EngineeringGoalLifecycle(
            repo_root=self.repo_root,
            payload=payload,
            plan=_as_mapping(plan_event.get("multi_step_plan")),
            raw_steps=[dict(item) for item in plan_event.get("steps", []) if isinstance(item, Mapping)],
        )
        memory = self.memory_store.load_relevant_memory(goal=_clean_text(payload.get("goal")))
        return lifecycle.load_or_create(memory)

    def _lifecycle_for_payload(self, payload: Mapping[str, Any]) -> EngineeringGoalLifecycle:
        return EngineeringGoalLifecycle(
            repo_root=self.repo_root,
            payload=payload,
            plan=build_multi_step_plan(payload),
            raw_steps=[dict(item) for item in payload.get("steps", []) if isinstance(item, Mapping)]
            if isinstance(payload.get("steps"), list)
            else [],
        )

    def _replan_reason(self, continuation: Mapping[str, Any], lifecycle: Mapping[str, Any]) -> str:
        goal_state = _clean_text(lifecycle.get("goal_state")).lower()
        if goal_state == "completed":
            return ""
        if lifecycle.get("blocked_tasks"):
            return "blocked_task"
        remaining = lifecycle.get("remaining_tasks")
        if isinstance(remaining, list) and not remaining and goal_state not in {"completed", "failed", "cancelled"}:
            return "tasks_exhausted_goal_incomplete"

        latest = _as_mapping(continuation.get("latest_result"))
        bundle = _as_mapping(latest.get("result_bundle"))
        if bool(latest.get("follow_up_planning_requested")) or bool(bundle.get("follow_up_planning_requested")):
            return "execution_result_requests_follow_up_planning"
        for decision in bundle.get("decisions", []) if isinstance(bundle.get("decisions"), list) else []:
            if isinstance(decision, Mapping) and _clean_text(decision.get("next_action")).lower() in {"plan_follow_up", "follow_up_planning"}:
                return "execution_result_requests_follow_up_planning"
        return ""


def run_engineering_planning_loop(
    payload: Mapping[str, Any],
    *,
    repo_root: str | Path,
    max_replans: int = 2,
) -> dict[str, Any]:
    return EngineeringPlanningLoop(repo_root=repo_root, max_replans=max_replans).run(payload)


__all__ = [
    "ENGINEERING_PLANNING_LOOP_SCHEMA",
    "EngineeringPlanningLoop",
    "run_engineering_planning_loop",
]
