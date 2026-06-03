from __future__ import annotations

"""Automatic continuation for engineering goals.

The coordinator owns no execution, lifecycle, or memory logic. It only loops
over the existing lifecycle-aware EngineeringTaskRunner entrypoint until the
persisted goal lifecycle reaches a terminal state.
"""

import copy
import json
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from core.tasks.engineering_goal_lifecycle import GOAL_STATE_SCHEMA, lifecycle_enabled
from core.tasks.engineering_task_runner import run_engineering_task


GOAL_CONTINUATION_SCHEMA = "zero.engineering_goal.continuation.v1"
TERMINAL_GOAL_STATES = {"completed", "blocked", "failed", "cancelled"}


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _task_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    package = payload.get("package")
    if isinstance(package, Mapping):
        return dict(package)
    return dict(payload)


class GoalContinuationCoordinator:
    """Orchestrates GoalLifecycle -> EngineeringTaskRunner -> GoalLifecycle."""

    def __init__(
        self,
        *,
        repo_root: str | Path,
        task_runner: Callable[[Mapping[str, Any]], dict[str, Any]] | None = None,
        max_cycles: int = 100,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.max_cycles = max(1, int(max_cycles or 1))
        if task_runner is None:
            self._task_runner = lambda payload: run_engineering_task(payload, repo_root=self.repo_root)
        else:
            self._task_runner = task_runner

    @property
    def state_dir(self) -> Path:
        return self.repo_root / "workspace" / "work_packages"

    def load_active_goals(self) -> list[dict[str, Any]]:
        goals: list[dict[str, Any]] = []
        for path in sorted(self.state_dir.glob("*.engineering_goal_state.json")):
            state = _read_json(path)
            if state.get("schema") != GOAL_STATE_SCHEMA:
                continue
            if _clean_text(state.get("goal_state")).lower() in TERMINAL_GOAL_STATES:
                continue
            state["state_path"] = str(path)
            goals.append(state)
        return goals

    def continue_active_goals(
        self,
        payloads: list[Mapping[str, Any]],
        *,
        max_cycles: int | None = None,
    ) -> dict[str, Any]:
        results = [
            self.continue_goal(payload, max_cycles=max_cycles)
            for payload in payloads
            if lifecycle_enabled(_task_payload(payload))
        ]
        return {
            "schema": GOAL_CONTINUATION_SCHEMA,
            "ok": all(bool(item.get("ok")) for item in results) if results else True,
            "mode": "goal_continuation_coordinator",
            "goal_count": len(results),
            "active_goals_loaded": len(self.load_active_goals()),
            "results": results,
            "terminal": all(bool(item.get("terminal")) for item in results) if results else True,
        }

    def continue_goal(
        self,
        payload: Mapping[str, Any],
        *,
        max_cycles: int | None = None,
    ) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise ValueError("goal_continuation_payload_must_be_mapping")
        if not lifecycle_enabled(_task_payload(payload)):
            raise ValueError("goal_continuation_requires_lifecycle_enabled_payload")

        cycle_limit = max(1, int(max_cycles or self.max_cycles))
        working_payload = copy.deepcopy(dict(payload))
        working_payload.pop("resume", None)
        if isinstance(working_payload.get("package"), dict):
            working_payload["package"] = copy.deepcopy(working_payload["package"])
            working_payload["package"].pop("resume", None)

        cycles: list[dict[str, Any]] = []
        latest_result: dict[str, Any] = {}
        latest_state: dict[str, Any] = {}
        stopped_reason = "max_cycles_reached"

        for cycle_index in range(1, cycle_limit + 1):
            active_before = self.load_active_goals()
            result = self._task_runner(copy.deepcopy(working_payload))
            latest_result = copy.deepcopy(result if isinstance(result, dict) else {})
            result_bundle = latest_result.get("result_bundle") if isinstance(latest_result.get("result_bundle"), dict) else {}
            lifecycle_state = (
                result_bundle.get("goal_lifecycle")
                if isinstance(result_bundle.get("goal_lifecycle"), dict)
                else latest_result.get("goal_lifecycle")
                if isinstance(latest_result.get("goal_lifecycle"), dict)
                else {}
            )
            latest_state = copy.deepcopy(lifecycle_state if isinstance(lifecycle_state, dict) else {})
            goal_state = _clean_text(latest_state.get("goal_state"), "unknown").lower()
            cycles.append(
                {
                    "cycle": cycle_index,
                    "submitted_to": "core.tasks.engineering_task_runner.run_engineering_task",
                    "ok": bool(latest_result.get("ok")),
                    "package_id": _clean_text(latest_result.get("package_id")),
                    "goal_state": goal_state,
                    "selected_task": copy.deepcopy(latest_state.get("selected_task") if isinstance(latest_state.get("selected_task"), dict) else {}),
                    "completed_tasks": copy.deepcopy(latest_state.get("completed_tasks") if isinstance(latest_state.get("completed_tasks"), list) else []),
                    "remaining_tasks": copy.deepcopy(latest_state.get("remaining_tasks") if isinstance(latest_state.get("remaining_tasks"), list) else []),
                    "active_goals_before": len(active_before),
                }
            )
            if goal_state in TERMINAL_GOAL_STATES:
                stopped_reason = goal_state
                break
            if not latest_result.get("ok") and goal_state not in {"next_task_generated", "task_selected", "running"}:
                stopped_reason = "runner_stopped_without_continuable_goal"
                break

        terminal = _clean_text(latest_state.get("goal_state")).lower() in TERMINAL_GOAL_STATES
        return {
            "schema": GOAL_CONTINUATION_SCHEMA,
            "ok": terminal and _clean_text(latest_state.get("goal_state")).lower() == "completed",
            "mode": "goal_continuation_coordinator",
            "terminal": terminal,
            "stopped_reason": stopped_reason,
            "cycle_count": len(cycles),
            "cycles": cycles,
            "goal_lifecycle": latest_state,
            "engineering_goal_lifecycle": copy.deepcopy(latest_state),
            "latest_result": latest_result,
            "active_goals": self.load_active_goals(),
            "updated_at": time.time(),
            "execution_path": {
                "orchestrates_only": True,
                "sequence": "GoalLifecycle -> EngineeringTaskRunner -> GoalLifecycle",
                "existing_aer_path_reused": True,
                "new_execution_path": False,
            },
        }


def continue_engineering_goal(
    payload: Mapping[str, Any],
    *,
    repo_root: str | Path,
    max_cycles: int = 100,
) -> dict[str, Any]:
    return GoalContinuationCoordinator(repo_root=repo_root, max_cycles=max_cycles).continue_goal(payload)


__all__ = [
    "GOAL_CONTINUATION_SCHEMA",
    "GoalContinuationCoordinator",
    "TERMINAL_GOAL_STATES",
    "continue_engineering_goal",
]
