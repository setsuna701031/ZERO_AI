from __future__ import annotations

import copy
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.runtime.recovery_replay_closure import run_multi_cycle_engineering_loop


SCHEMA = "zero.aer.persistent_runtime_orchestrator.v1"


def _now() -> float:
    return time.time()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_slug(value: Any, fallback: str = "persistent_runtime") -> str:
    text = _clean_text(value) or fallback
    cleaned = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in text)
    return cleaned.strip("_") or fallback


def _repo_root_from_value(value: Any) -> Path:
    if value is None:
        return Path(".").resolve()
    try:
        return Path(str(value)).resolve()
    except Exception:
        return Path(".").resolve()


def _runtime_root(repo_root: Path) -> Path:
    return Path(repo_root) / "workspace" / "persistent_runtime_orchestrator"


def _normalize_task_id(task: Dict[str, Any], fallback: str = "persistent_runtime_task") -> str:
    return (
        _clean_text(task.get("id"))
        or _clean_text(task.get("task_id"))
        or _clean_text(task.get("name"))
        or fallback
    )


def _is_persistent_runtime_task(task: Dict[str, Any]) -> bool:
    if not isinstance(task, dict):
        return False

    markers = (
        task.get("persistent_runtime"),
        task.get("long_running"),
        task.get("long_runtime"),
        task.get("multi_cycle"),
        task.get("aer_runtime"),
    )
    if any(bool(marker) for marker in markers):
        return True

    step_type = _clean_text(task.get("type") or task.get("step_type") or task.get("runtime_type")).lower()
    if step_type in {
        "persistent_runtime",
        "persistent_autonomous_engineering_runtime",
        "long_engineering_runtime",
        "multi_cycle_engineering_loop",
        "aer_persistent_runtime",
    }:
        return True

    mode = _clean_text(task.get("mode") or task.get("runtime_mode")).lower()
    if mode in {
        "persistent_runtime",
        "long_running",
        "multi_cycle",
        "aer_persistent_runtime",
    }:
        return True

    if isinstance(task.get("cycles"), list) and task.get("cycles"):
        return True

    goal = _clean_text(task.get("goal") or task.get("title") or task.get("task")).lower()
    if "persistent autonomous engineering runtime" in goal:
        return True
    if "long engineering runtime" in goal:
        return True
    if "multi-cycle" in goal or "multi cycle" in goal:
        return True
    if "failure" in goal and "recovery" in goal and "resume" in goal:
        return True

    return False


def should_route_persistent_runtime(task: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> bool:
    """Decide whether a task should enter the persistent runtime orchestrator.

    Boundary:
    - This is routing classification only.
    - It does not execute, mutate files, call tools, or bypass authority.
    """
    if _is_persistent_runtime_task(task):
        return True

    if isinstance(context, dict):
        for key in ("persistent_runtime", "long_running", "multi_cycle", "aer_runtime"):
            if bool(context.get(key)):
                return True
        mode = _clean_text(context.get("mode") or context.get("runtime_mode")).lower()
        if mode in {"persistent_runtime", "long_running", "multi_cycle", "aer_persistent_runtime"}:
            return True

    return False


def _normalize_group(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        text = _clean_text(item)
        if text:
            result.append(text)
    return result


def _normalize_cycles_from_task(task: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_cycles = task.get("cycles")
    if isinstance(raw_cycles, list) and raw_cycles:
        cycles: List[Dict[str, Any]] = []
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
                targets = _normalize_group(raw.get("targets"))
                if targets:
                    target_groups.append(targets)
            if not target_groups:
                goal = _clean_text(raw.get("goal") or raw.get("title") or f"cycle {index + 1}")
                target_groups.append([goal])

            cycles.append(
                {
                    "cycle_id": _clean_text(raw.get("cycle_id")) or f"cycle_{index + 1}",
                    "goal": _clean_text(raw.get("goal")) or _clean_text(raw.get("title")) or f"cycle {index + 1}",
                    "target_groups": target_groups,
                    "replan_hint": _clean_text(raw.get("replan_hint")),
                }
            )
        if cycles:
            return cycles

    target_groups: List[List[str]] = []
    raw_groups = task.get("target_groups") or task.get("plan_groups") or task.get("groups")
    if isinstance(raw_groups, list):
        for group in raw_groups:
            cleaned = _normalize_group(group)
            if cleaned:
                target_groups.append(cleaned)
    if not target_groups:
        targets = _normalize_group(task.get("targets"))
        if targets:
            target_groups.append(targets)
    if not target_groups:
        target_groups.append([_clean_text(task.get("goal") or task.get("title") or "persistent runtime task")])

    return [
        {
            "cycle_id": "cycle_1",
            "goal": _clean_text(task.get("goal")) or _clean_text(task.get("title")) or "persistent runtime task",
            "target_groups": target_groups,
            "replan_hint": "",
        }
    ]


class PersistentRuntimeOrchestrator:
    """Agent-facing persistent runtime orchestrator.

    This class is the stable boundary between AgentLoop and the deeper runtime
    closure layers.

    Ownership:
    - AgentLoop may route a long-running task here.
    - This orchestrator owns persistent session records and delegates to
      MultiCycleEngineeringLoop.
    - MultiCycleEngineeringLoop owns cycle execution and RecoveryReplayClosure.
    - LongEngineeringRuntime owns checkpoints and failure/resume markers.
    - StepExecutor and execution_gateway remain execution endpoints, not session
      orchestrators.

    This prevents execution_gateway.py and step_executor.py from absorbing
    session/recovery/multi-cycle responsibilities.
    """

    def __init__(self, repo_root: Path | str = ".") -> None:
        self.repo_root = _repo_root_from_value(repo_root)
        self.root = _runtime_root(self.repo_root)

    def _session_dir(self, session_id: str) -> Path:
        return self.root / session_id

    def _new_session_id(self, task_id: str) -> str:
        return f"persistent_runtime_{_safe_slug(task_id)}_{uuid.uuid4().hex[:12]}"

    def _write_session_record(self, session_dir: Path, record: Dict[str, Any]) -> None:
        record["updated_at"] = _now()
        record["session_dir"] = str(session_dir)
        record["session_record_path"] = str(session_dir / "orchestrator_session.json")
        _write_json(session_dir / "orchestrator_session.json", record)

    def run(
        self,
        *,
        task: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        executor: Optional[Any] = None,
        fail_cycle_index: int = -1,
        fail_group_index: int = -1,
        force: bool = False,
    ) -> Dict[str, Any]:
        normalized_task = copy.deepcopy(task) if isinstance(task, dict) else {}
        normalized_context = copy.deepcopy(context) if isinstance(context, dict) else {}

        if not force and not should_route_persistent_runtime(normalized_task, normalized_context):
            return {
                "ok": False,
                "schema": SCHEMA,
                "status": "not_persistent_runtime_task",
                "reason": "task did not match persistent runtime routing policy",
                "routed": False,
                "created_at": _now(),
            }

        task_id = _normalize_task_id(normalized_task)
        session_id = self._new_session_id(task_id)
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        cycles = _normalize_cycles_from_task(normalized_task)
        goal = _clean_text(normalized_task.get("goal") or normalized_task.get("title") or task_id)

        record: Dict[str, Any] = {
            "ok": True,
            "schema": SCHEMA,
            "session_id": session_id,
            "task_id": task_id,
            "goal": goal,
            "status": "running",
            "routed": True,
            "created_at": _now(),
            "updated_at": _now(),
            "task": normalized_task,
            "context": normalized_context,
            "cycles": cycles,
            "boundary": {
                "agent_loop_entry_boundary": True,
                "delegates_to_multi_cycle_engineering_loop": True,
                "does_not_modify_execution_gateway": True,
                "does_not_modify_step_executor": True,
                "does_not_bypass_authority": True,
                "does_not_execute_hidden_mutations": True,
            },
        }
        self._write_session_record(session_dir, record)

        loop_result = run_multi_cycle_engineering_loop(
            repo_root=self.repo_root,
            task={
                **normalized_task,
                "id": task_id,
                "goal": goal,
                "cycles": cycles,
                "persistent_runtime_session_id": session_id,
            },
            result={},
            cycles=cycles,
            executor=executor,
            fail_cycle_index=fail_cycle_index,
            fail_group_index=fail_group_index,
        )

        multi_cycle = loop_result.get("multi_cycle_engineering_loop", {})
        if not isinstance(multi_cycle, dict):
            multi_cycle = {}

        record["multi_cycle_engineering_loop"] = multi_cycle
        record["multi_cycle_engineering_loop_result"] = loop_result
        record["ok"] = bool(loop_result.get("ok"))
        record["status"] = "finished" if bool(loop_result.get("ok")) else "failed"
        record["finished_at"] = _now()
        self._write_session_record(session_dir, record)

        return self._finalize(record, session_dir)

    def _finalize(self, record: Dict[str, Any], session_dir: Path) -> Dict[str, Any]:
        multi_cycle = record.get("multi_cycle_engineering_loop")
        if not isinstance(multi_cycle, dict):
            multi_cycle = {}
        return {
            "ok": bool(record.get("ok")),
            "schema": SCHEMA,
            "status": record.get("status"),
            "routed": bool(record.get("routed")),
            "session_id": record.get("session_id"),
            "task_id": record.get("task_id"),
            "goal": record.get("goal"),
            "session_dir": str(session_dir),
            "session_record_path": str(session_dir / "orchestrator_session.json"),
            "multi_cycle_engineering_loop": multi_cycle,
            "cycle_count": multi_cycle.get("cycle_count", 0),
            "cycle_result_count": multi_cycle.get("cycle_result_count", 0),
            "closure_count": multi_cycle.get("closure_count", 0),
            "boundary": record.get("boundary", {}),
        }


def run_persistent_runtime_orchestrator(
    *,
    repo_root: Path | str = ".",
    task: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    executor: Optional[Any] = None,
    fail_cycle_index: int = -1,
    fail_group_index: int = -1,
    force: bool = False,
) -> Dict[str, Any]:
    current_result: Dict[str, Any] = result if isinstance(result, dict) else {}
    orchestrator = PersistentRuntimeOrchestrator(repo_root=repo_root)
    orchestrator_result = orchestrator.run(
        task=task,
        context=context,
        executor=executor,
        fail_cycle_index=fail_cycle_index,
        fail_group_index=fail_group_index,
        force=force,
    )
    current_result["persistent_runtime_orchestrator"] = orchestrator_result
    current_result["persistent_runtime_orchestrator_ok"] = bool(orchestrator_result.get("ok"))
    current_result["persistent_runtime_orchestrator_status"] = orchestrator_result.get("status")
    current_result["persistent_runtime_orchestrator_session_id"] = orchestrator_result.get("session_id", "")
    current_result["persistent_runtime_orchestrator_routed"] = bool(orchestrator_result.get("routed"))
    current_result["ok"] = bool(orchestrator_result.get("ok"))
    return current_result


__all__ = [
    "SCHEMA",
    "PersistentRuntimeOrchestrator",
    "run_persistent_runtime_orchestrator",
    "should_route_persistent_runtime",
]
