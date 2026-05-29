from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.runtime.long_engineering_runtime import (
    execute_long_engineering_runtime,
    find_latest_long_runtime_recovery,
    normalize_runtime_plan_groups,
    resume_long_engineering_runtime,
)


SCHEMA = "zero.aer.recovery_replay_closure.v1"
MULTI_CYCLE_SCHEMA = "zero.aer.multi_cycle_engineering_loop.v1"


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


def _normalize_task_id(task: Dict[str, Any], fallback: str = "recovery_replay_task") -> str:
    return (
        _clean_text(task.get("id"))
        or _clean_text(task.get("task_id"))
        or _clean_text(task.get("name"))
        or fallback
    )


def _runtime_root(repo_root: Path) -> Path:
    return Path(repo_root) / "workspace" / "recovery_replay_closure"


def _summarize_runtime_result(result: Dict[str, Any]) -> Dict[str, Any]:
    runtime = result.get("long_engineering_runtime")
    if not isinstance(runtime, dict):
        return {"ok": bool(result.get("ok")), "status": result.get("status", "unknown")}

    return {
        "ok": bool(runtime.get("ok")),
        "status": runtime.get("status"),
        "session_id": runtime.get("session_id"),
        "session_journal_path": runtime.get("session_journal_path"),
        "session_state_path": runtime.get("session_state_path"),
        "recoverable": bool(runtime.get("recoverable")),
        "recovery_marker_path": runtime.get("recovery_marker_path", ""),
        "checkpoint_count": runtime.get("checkpoint_count", 0),
        "executed_group_count": runtime.get("executed_group_count", 0),
        "plan_group_count": runtime.get("plan_group_count", 0),
    }


class RecoveryReplayClosure:
    """File-backed closure for failure -> recovery marker -> resume."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = Path(repo_root)
        self.root = _runtime_root(self.repo_root)
        self.closure_log_path = self.root / "closure_log.json"

    def _load_log(self) -> Dict[str, Any]:
        data = _read_json(self.closure_log_path)
        if data:
            return data
        return {
            "ok": True,
            "schema": SCHEMA,
            "created_at": _now(),
            "updated_at": _now(),
            "closures": [],
        }

    def _write_log(self, data: Dict[str, Any]) -> None:
        data["updated_at"] = _now()
        _write_json(self.closure_log_path, data)

    def close_latest(
        self,
        *,
        task: Dict[str, Any],
        task_id: str = "",
        goal: str = "",
        executor: Optional[Any] = None,
    ) -> Dict[str, Any]:
        marker = find_latest_long_runtime_recovery(self.repo_root)
        if not marker:
            record = {
                "ok": False,
                "schema": SCHEMA,
                "status": "no_recoverable_session",
                "reason": "no long runtime recovery marker found",
                "created_at": _now(),
            }
            log = self._load_log()
            log.setdefault("closures", []).append(record)
            self._write_log(log)
            return record

        source_session_id = _clean_text(marker.get("session_id"))
        resume_result = resume_long_engineering_runtime(
            repo_root=self.repo_root,
            task=task,
            result={},
            task_id=task_id or _normalize_task_id(task, "recovery_replay_resume"),
            goal=goal or _clean_text(task.get("goal")) or "recovery replay closure",
            source_session_id=source_session_id,
            executor=executor,
        )
        resume = resume_result.get("long_engineering_runtime_resume", {})
        if not isinstance(resume, dict):
            resume = {}

        record = {
            "ok": bool(resume.get("ok")),
            "schema": SCHEMA,
            "status": "closed" if bool(resume.get("ok")) else "closure_failed",
            "source_session_id": source_session_id,
            "source_recovery_marker": marker,
            "resume": resume,
            "resumed_session_id": resume.get("resumed_session_id"),
            "closure_log_path": str(self.closure_log_path),
            "created_at": _now(),
            "boundary": {
                "uses_recovery_marker": True,
                "creates_linked_resumed_session": True,
                "does_not_bypass_step_executor": True,
                "does_not_change_scheduler_authority": True,
            },
        }

        log = self._load_log()
        log.setdefault("closures", []).append(record)
        self._write_log(log)
        return record


def close_latest_recovery_replay(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    result: Optional[Dict[str, Any]] = None,
    task_id: str = "",
    goal: str = "",
    executor: Optional[Any] = None,
) -> Dict[str, Any]:
    current_result: Dict[str, Any] = result if isinstance(result, dict) else {}
    closure = RecoveryReplayClosure(repo_root)
    closure_result = closure.close_latest(
        task=task,
        task_id=task_id,
        goal=goal,
        executor=executor,
    )
    current_result["recovery_replay_closure"] = closure_result
    current_result["recovery_replay_closure_ok"] = bool(closure_result.get("ok"))
    current_result["recovery_replay_closure_status"] = closure_result.get("status")
    current_result["ok"] = bool(closure_result.get("ok"))
    return current_result


class MultiCycleEngineeringLoop:
    """Persistent multi-cycle engineering loop over long-runtime sessions."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = Path(repo_root)
        self.root = Path(repo_root) / "workspace" / "multi_cycle_engineering_loop"
        self.loop_log_path = self.root / "multi_cycle_loop.json"

    def _new_loop_record(self, task: Dict[str, Any], cycles: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "ok": True,
            "schema": MULTI_CYCLE_SCHEMA,
            "task_id": _normalize_task_id(task, "multi_cycle_task"),
            "goal": _clean_text(task.get("goal")) or _clean_text(task.get("title")) or "multi-cycle engineering loop",
            "status": "running",
            "created_at": _now(),
            "updated_at": _now(),
            "cycles": cycles,
            "cycle_results": [],
            "closure_results": [],
            "boundary": {
                "uses_long_engineering_runtime": True,
                "uses_recovery_replay_closure": True,
                "does_not_execute_hidden_mutations": True,
                "operator_authority_is_not_modified": True,
            },
        }

    def _write_loop_record(self, record: Dict[str, Any]) -> None:
        record["updated_at"] = _now()
        record["loop_log_path"] = str(self.loop_log_path)
        _write_json(self.loop_log_path, record)

    def _normalize_cycles(self, task: Dict[str, Any], cycles: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        if isinstance(cycles, list) and cycles:
            cleaned_cycles: List[Dict[str, Any]] = []
            for index, cycle in enumerate(cycles):
                if not isinstance(cycle, dict):
                    continue
                cleaned_cycles.append(
                    {
                        "cycle_id": _clean_text(cycle.get("cycle_id")) or f"cycle_{index + 1}",
                        "goal": _clean_text(cycle.get("goal")) or _clean_text(cycle.get("title")),
                        "target_groups": normalize_runtime_plan_groups(cycle),
                        "replan_hint": _clean_text(cycle.get("replan_hint")),
                    }
                )
            if cleaned_cycles:
                return cleaned_cycles

        task_cycles = task.get("cycles")
        if isinstance(task_cycles, list) and task_cycles:
            return self._normalize_cycles(task, [cycle for cycle in task_cycles if isinstance(cycle, dict)])

        return [
            {
                "cycle_id": "cycle_1",
                "goal": _clean_text(task.get("goal")) or _clean_text(task.get("title")) or "multi-cycle engineering loop",
                "target_groups": normalize_runtime_plan_groups(task),
                "replan_hint": "",
            }
        ]

    def _cycle_task(self, task: Dict[str, Any], cycle: Dict[str, Any], cycle_index: int) -> Dict[str, Any]:
        cycle_task = dict(task)
        cycle_task["id"] = f"{_normalize_task_id(task, 'multi_cycle_task')}_cycle_{cycle_index + 1}"
        cycle_task["goal"] = _clean_text(cycle.get("goal")) or _clean_text(task.get("goal")) or "multi-cycle engineering loop"
        cycle_task["target_groups"] = cycle.get("target_groups") if isinstance(cycle.get("target_groups"), list) else []
        cycle_task["cycle_index"] = cycle_index
        cycle_task["cycle_id"] = cycle.get("cycle_id") or f"cycle_{cycle_index + 1}"
        cycle_task["replan_hint"] = cycle.get("replan_hint", "")
        return cycle_task

    def run(
        self,
        *,
        task: Dict[str, Any],
        cycles: Optional[List[Dict[str, Any]]] = None,
        executor: Optional[Any] = None,
        fail_cycle_index: int = -1,
        fail_group_index: int = -1,
        stop_on_unclosed_failure: bool = True,
    ) -> Dict[str, Any]:
        normalized_cycles = self._normalize_cycles(task, cycles)
        record = self._new_loop_record(task, normalized_cycles)
        self.root.mkdir(parents=True, exist_ok=True)
        self._write_loop_record(record)

        for cycle_index, cycle in enumerate(normalized_cycles):
            cycle_task = self._cycle_task(task, cycle, cycle_index)
            cycle_fail_group = fail_group_index if cycle_index == fail_cycle_index else -1

            cycle_result = execute_long_engineering_runtime(
                repo_root=self.repo_root,
                task=cycle_task,
                result={},
                task_id=f"{record['task_id']}_cycle_{cycle_index + 1}",
                goal=_clean_text(cycle.get("goal")) or record["goal"],
                executor=executor,
                fail_group_index=cycle_fail_group,
            )
            cycle_summary = {
                "cycle_index": cycle_index,
                "cycle_id": cycle.get("cycle_id") or f"cycle_{cycle_index + 1}",
                "cycle": cycle,
                "runtime": _summarize_runtime_result(cycle_result),
                "raw_result": cycle_result,
                "created_at": _now(),
            }
            record.setdefault("cycle_results", []).append(cycle_summary)
            self._write_loop_record(record)

            if not bool(cycle_result.get("ok")):
                closure_result = close_latest_recovery_replay(
                    repo_root=self.repo_root,
                    task=cycle_task,
                    result={},
                    task_id=f"{record['task_id']}_cycle_{cycle_index + 1}_resume",
                    goal=f"{record['goal']} / recovery replay closure",
                    executor=executor,
                )
                closure_summary = {
                    "cycle_index": cycle_index,
                    "cycle_id": cycle_summary["cycle_id"],
                    "closure": closure_result.get("recovery_replay_closure", {}),
                    "raw_result": closure_result,
                    "created_at": _now(),
                }
                record.setdefault("closure_results", []).append(closure_summary)
                self._write_loop_record(record)

                if not bool(closure_result.get("ok")) and stop_on_unclosed_failure:
                    record["ok"] = False
                    record["status"] = "blocked_unclosed_failure"
                    record["blocked_cycle_index"] = cycle_index
                    self._write_loop_record(record)
                    return self._finalize(record)

        record["ok"] = True
        record["status"] = "finished"
        record["finished_at"] = _now()
        self._write_loop_record(record)
        return self._finalize(record)

    def _finalize(self, record: Dict[str, Any]) -> Dict[str, Any]:
        cycle_results = record.get("cycle_results") if isinstance(record.get("cycle_results"), list) else []
        closure_results = record.get("closure_results") if isinstance(record.get("closure_results"), list) else []
        cycles = record.get("cycles") if isinstance(record.get("cycles"), list) else []
        return {
            "ok": bool(record.get("ok")),
            "schema": record.get("schema"),
            "status": record.get("status"),
            "task_id": record.get("task_id"),
            "goal": record.get("goal"),
            "loop_log_path": str(self.loop_log_path),
            "cycle_count": len(cycles),
            "cycle_result_count": len(cycle_results),
            "closure_count": len(closure_results),
            "cycle_results": cycle_results,
            "closure_results": closure_results,
            "boundary": record.get("boundary", {}),
        }


def run_multi_cycle_engineering_loop(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    result: Optional[Dict[str, Any]] = None,
    cycles: Optional[List[Dict[str, Any]]] = None,
    executor: Optional[Any] = None,
    fail_cycle_index: int = -1,
    fail_group_index: int = -1,
    stop_on_unclosed_failure: bool = True,
) -> Dict[str, Any]:
    current_result: Dict[str, Any] = result if isinstance(result, dict) else {}
    loop = MultiCycleEngineeringLoop(repo_root)
    loop_result = loop.run(
        task=task,
        cycles=cycles,
        executor=executor,
        fail_cycle_index=fail_cycle_index,
        fail_group_index=fail_group_index,
        stop_on_unclosed_failure=stop_on_unclosed_failure,
    )
    current_result["multi_cycle_engineering_loop"] = loop_result
    current_result["multi_cycle_engineering_loop_ok"] = bool(loop_result.get("ok"))
    current_result["multi_cycle_engineering_loop_status"] = loop_result.get("status")
    current_result["multi_cycle_engineering_loop_log_path"] = loop_result.get("loop_log_path")
    current_result["ok"] = bool(loop_result.get("ok"))
    return current_result


__all__ = [
    "SCHEMA",
    "MULTI_CYCLE_SCHEMA",
    "RecoveryReplayClosure",
    "MultiCycleEngineeringLoop",
    "close_latest_recovery_replay",
    "run_multi_cycle_engineering_loop",
]
