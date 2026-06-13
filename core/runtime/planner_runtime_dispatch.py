from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.runtime.persistent_runtime_orchestrator import (
    run_persistent_runtime_orchestrator,
    should_route_persistent_runtime,
)
from core.reports.engineering_report_contract import attach_engineering_report


SCHEMA = "zero.aer.planner_runtime_dispatch.v1"


def _now() -> float:
    return time.time()


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _safe_short_id(value: Any, fallback: str = "planner_runtime_task") -> str:
    text = _clean_text(value) or fallback
    digest = str(abs(hash(text)))[-8:]
    lowered = text.lower()
    if "recovery" in lowered and "resume" in lowered:
        return f"planner_prt_recovery_{digest}"
    if "persistent" in lowered or "runtime" in lowered:
        return f"planner_prt_{digest}"
    return f"planner_prt_task_{digest}"


def _normalize_group(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        text = _clean_text(item)
        if text:
            result.append(text)
    return result


def _extract_steps_from_plan(plan: Any) -> List[Dict[str, Any]]:
    if not isinstance(plan, dict):
        return []

    for key in ("steps", "plan_steps", "actions", "tasks"):
        value = plan.get(key)
        if isinstance(value, list):
            return [copy.deepcopy(item) for item in value if isinstance(item, dict)]

    nested_plan = plan.get("plan")
    if isinstance(nested_plan, dict):
        return _extract_steps_from_plan(nested_plan)

    return []


def _step_to_group(step: Dict[str, Any], index: int) -> List[str]:
    candidates = [
        step.get("description"),
        step.get("goal"),
        step.get("title"),
        step.get("name"),
        step.get("task"),
        step.get("action"),
        step.get("type"),
    ]
    group: List[str] = []
    for candidate in candidates:
        text = _clean_text(candidate)
        if text and text not in group:
            group.append(text)

    targets = step.get("targets")
    if isinstance(targets, list):
        for target in targets:
            text = _clean_text(target)
            if text and text not in group:
                group.append(text)

    target_file = _clean_text(step.get("target_file") or step.get("path") or step.get("file"))
    if target_file and target_file not in group:
        group.append(target_file)

    if not group:
        group = [f"planner step {index + 1}"]

    return group


def _plan_declares_persistent_runtime(plan: Dict[str, Any]) -> bool:
    markers = (
        plan.get("persistent_runtime"),
        plan.get("long_running"),
        plan.get("long_runtime"),
        plan.get("multi_cycle"),
        plan.get("aer_runtime"),
    )
    if any(bool(marker) for marker in markers):
        return True

    mode = _clean_text(plan.get("mode") or plan.get("runtime_mode") or plan.get("planner_mode")).lower()
    if mode in {
        "persistent_runtime",
        "long_running",
        "multi_cycle",
        "aer_persistent_runtime",
        "persistent_autonomous_engineering_runtime",
    }:
        return True

    runtime = plan.get("runtime")
    if isinstance(runtime, dict):
        if any(bool(runtime.get(key)) for key in ("persistent", "long_running", "multi_cycle", "aer_runtime")):
            return True
        runtime_mode = _clean_text(runtime.get("mode") or runtime.get("type")).lower()
        if runtime_mode in {"persistent_runtime", "long_running", "multi_cycle"}:
            return True

    cycles = plan.get("cycles")
    if isinstance(cycles, list) and cycles:
        return True

    goal = _clean_text(plan.get("goal") or plan.get("title") or plan.get("summary")).lower()
    if "persistent autonomous engineering runtime" in goal:
        return True
    if "long engineering runtime" in goal:
        return True
    if "multi-cycle" in goal or "multi cycle" in goal:
        return True
    if "failure" in goal and "recovery" in goal and "resume" in goal:
        return True

    return False


def planner_result_to_persistent_runtime_task(
    *,
    user_input: str,
    planner_result: Dict[str, Any],
    task_id: str = "",
) -> Dict[str, Any]:
    """Convert a planner result into a PersistentRuntimeOrchestrator task.

    Boundary:
    - This converter does not execute.
    - It does not mutate source files.
    - It only transforms planner output into stable runtime cycles.
    """
    plan = copy.deepcopy(planner_result) if isinstance(planner_result, dict) else {}
    goal = (
        _clean_text(plan.get("goal"))
        or _clean_text(plan.get("title"))
        or _clean_text(plan.get("summary"))
        or _clean_text(user_input)
        or "planner persistent runtime task"
    )

    cycles: List[Dict[str, Any]] = []
    raw_cycles = plan.get("cycles")
    if isinstance(raw_cycles, list) and raw_cycles:
        for index, raw in enumerate(raw_cycles):
            if not isinstance(raw, dict):
                continue
            target_groups: List[List[str]] = []
            raw_groups = raw.get("target_groups") or raw.get("plan_groups") or raw.get("groups")
            if isinstance(raw_groups, list):
                for group in raw_groups:
                    cleaned = _normalize_group(group)
                    if cleaned:
                        target_groups.append(cleaned)

            if not target_groups:
                steps = _extract_steps_from_plan(raw)
                for step_index, step in enumerate(steps):
                    target_groups.append(_step_to_group(step, step_index))

            if not target_groups:
                targets = _normalize_group(raw.get("targets"))
                if targets:
                    target_groups.append(targets)

            if not target_groups:
                target_groups = [[_clean_text(raw.get("goal") or raw.get("title") or f"cycle {index + 1}")]]

            cycles.append(
                {
                    "cycle_id": _clean_text(raw.get("cycle_id")) or f"planner_cycle_{index + 1}",
                    "goal": _clean_text(raw.get("goal")) or _clean_text(raw.get("title")) or goal,
                    "target_groups": target_groups,
                    "replan_hint": _clean_text(raw.get("replan_hint")),
                }
            )

    if not cycles:
        steps = _extract_steps_from_plan(plan)
        if steps:
            cycles = [
                {
                    "cycle_id": "planner_cycle_1",
                    "goal": goal,
                    "target_groups": [_step_to_group(step, index) for index, step in enumerate(steps)],
                    "replan_hint": _clean_text(plan.get("replan_hint")),
                }
            ]

    if not cycles:
        target_groups: List[List[str]] = []
        raw_groups = plan.get("target_groups") or plan.get("plan_groups") or plan.get("groups")
        if isinstance(raw_groups, list):
            for group in raw_groups:
                cleaned = _normalize_group(group)
                if cleaned:
                    target_groups.append(cleaned)
        if not target_groups:
            target_groups = [[goal]]

        cycles = [
            {
                "cycle_id": "planner_cycle_1",
                "goal": goal,
                "target_groups": target_groups,
                "replan_hint": _clean_text(plan.get("replan_hint")),
            }
        ]

    planner_steps = _extract_steps_from_plan(plan)

    return {
        "id": _clean_text(task_id) or _safe_short_id(goal),
        "goal": goal,
        "persistent_runtime": True,
        "aer_runtime": True,
        "mode": "persistent_runtime",
        "type": "planner_persistent_runtime_dispatch",
        "source": "planner_runtime_dispatch",
        "user_input": _clean_text(user_input),
        "planner_result": plan,
        "planner_steps": planner_steps,
        "steps": copy.deepcopy(planner_steps),
        "cycles": cycles,
        "boundary": {
            "planner_output_conversion_only": True,
            "orchestrator_owns_long_loop": True,
            "agent_loop_routes_only": True,
            "step_executor_remains_execution_endpoint": True,
            "execution_gateway_remains_execution_endpoint": True,
            "short_task_id_for_windows_path_safety": True,
        },
    }


def should_dispatch_planner_result_to_persistent_runtime(
    *,
    user_input: str,
    planner_result: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
) -> bool:
    if not isinstance(planner_result, dict):
        return False

    if _plan_declares_persistent_runtime(planner_result):
        return True

    if isinstance(context, dict):
        if any(bool(context.get(key)) for key in ("persistent_runtime", "long_running", "multi_cycle", "aer_runtime")):
            return True
        mode = _clean_text(context.get("mode") or context.get("runtime_mode")).lower()
        if mode in {"persistent_runtime", "long_running", "multi_cycle", "aer_persistent_runtime"}:
            return True

    text = _clean_text(user_input).lower()
    markers = (
        "persistent autonomous engineering runtime",
        "persistent runtime",
        "long engineering runtime",
        "multi-cycle",
        "multi cycle",
        "failure recovery resume",
        "failure -> recovery -> resume",
    )
    return any(marker in text for marker in markers)


class PlannerRuntimeDispatcher:
    """Dispatch planner results into PersistentRuntimeOrchestrator.

    This is the explicit bridge for:

        natural language -> planner result -> cycles -> persistent runtime

    It intentionally remains separate from planner.py, agent_loop.py,
    step_executor.py, and execution_gateway.py to avoid responsibility creep.
    """

    def __init__(self, repo_root: Path | str = ".") -> None:
        self.repo_root = Path(str(repo_root)).resolve()
        self.root = self.repo_root / "workspace" / "planner_runtime_dispatch"
        self.dispatch_log_path = self.root / "dispatch_log.json"

    def _load_log(self) -> Dict[str, Any]:
        if not self.dispatch_log_path.exists():
            return {
                "ok": True,
                "schema": SCHEMA,
                "created_at": _now(),
                "updated_at": _now(),
                "dispatches": [],
            }
        try:
            data = json.loads(self.dispatch_log_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault("ok", True)
        data.setdefault("schema", SCHEMA)
        data.setdefault("dispatches", [])
        return data

    def _write_log(self, log: Dict[str, Any]) -> None:
        log["updated_at"] = _now()
        _write_json(self.dispatch_log_path, log)

    def dispatch(
        self,
        *,
        user_input: str,
        planner_result: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        executor: Optional[Any] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        if not force and not should_dispatch_planner_result_to_persistent_runtime(
            user_input=user_input,
            planner_result=planner_result,
            context=context,
        ):
            record = {
                "ok": False,
                "schema": SCHEMA,
                "status": "not_persistent_runtime_plan",
                "routed": False,
                "reason": "planner result did not request persistent runtime dispatch",
                "created_at": _now(),
            }
            log = self._load_log()
            log.setdefault("dispatches", []).append(record)
            self._write_log(log)
            return record

        task = planner_result_to_persistent_runtime_task(
            user_input=user_input,
            planner_result=planner_result,
        )
        workspace_root = self.repo_root / "workspace"
        task["repo_root"] = str(self.repo_root)
        task["workspace_root"] = str(workspace_root)
        task["workspace_dir"] = str(workspace_root)
        task["shared_dir"] = str(workspace_root / "shared")

        orchestrator_payload = run_persistent_runtime_orchestrator(
            repo_root=self.repo_root,
            workspace_dir=workspace_root,
            task=task,
            context={
                **(copy.deepcopy(context) if isinstance(context, dict) else {}),
                "source": "planner_runtime_dispatch",
                "planner_runtime_dispatch": True,
                "persistent_runtime": True,
                "repo_root": str(self.repo_root),
                "workspace_root": str(workspace_root),
                "shared_dir": str(workspace_root / "shared"),
            },
            result={},
            executor=executor,
            force=True,
        )
        orchestrator_result = orchestrator_payload.get("persistent_runtime_orchestrator", {})
        if not isinstance(orchestrator_result, dict):
            orchestrator_result = {}

        record = {
            "ok": bool(orchestrator_payload.get("ok")) and bool(orchestrator_result.get("ok")),
            "schema": SCHEMA,
            "status": "dispatched" if bool(orchestrator_payload.get("ok")) and bool(orchestrator_result.get("ok")) else "dispatch_failed",
            "routed": True,
            "task": task,
            "orchestrator": orchestrator_result,
            "orchestrator_payload": orchestrator_payload,
            "dispatch_log_path": str(self.dispatch_log_path),
            "created_at": _now(),
            "boundary": {
                "planner_result_to_cycles": True,
                "delegates_to_persistent_runtime_orchestrator": True,
                "does_not_modify_planner": True,
                "does_not_modify_step_executor": True,
                "does_not_modify_execution_gateway": True,
            },
        }
        record = attach_engineering_report(record, report_type="aer")

        log = self._load_log()
        log.setdefault("dispatches", []).append(record)
        self._write_log(log)
        return record


def dispatch_planner_result_to_persistent_runtime(
    *,
    repo_root: Path | str = ".",
    user_input: str,
    planner_result: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    executor: Optional[Any] = None,
    force: bool = False,
) -> Dict[str, Any]:
    current_result = result if isinstance(result, dict) else {}
    dispatcher = PlannerRuntimeDispatcher(repo_root=repo_root)
    dispatch_result = dispatcher.dispatch(
        user_input=user_input,
        planner_result=planner_result,
        context=context,
        executor=executor,
        force=force,
    )
    current_result["planner_runtime_dispatch"] = dispatch_result
    current_result["planner_runtime_dispatch_ok"] = bool(dispatch_result.get("ok"))
    current_result["planner_runtime_dispatch_status"] = dispatch_result.get("status")
    current_result["planner_runtime_dispatch_routed"] = bool(dispatch_result.get("routed"))
    current_result["ok"] = bool(dispatch_result.get("ok"))
    return current_result


__all__ = [
    "SCHEMA",
    "PlannerRuntimeDispatcher",
    "dispatch_planner_result_to_persistent_runtime",
    "planner_result_to_persistent_runtime_task",
    "should_dispatch_planner_result_to_persistent_runtime",
]
