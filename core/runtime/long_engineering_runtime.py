from __future__ import annotations

from core.runtime.runtime_status_canonicalization import canonical_runtime_status
from core.runtime.task_runtime import project_runtime_status
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


SCHEMA = "zero.aer.long_engineering_runtime.v1"


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


def _clean_group(group: Any) -> List[str]:
    if not isinstance(group, list):
        return []
    cleaned: List[str] = []
    for item in group:
        text = _clean_text(item)
        if text:
            cleaned.append(text)
    return cleaned


def _step_to_runtime_group(step: Any, index: int) -> List[str]:
    if not isinstance(step, dict):
        return []
    group: List[str] = []

    for key in ("description", "goal", "title", "name", "task", "action", "type", "tool"):
        text = _clean_text(step.get(key))
        if text and text not in group:
            group.append(text)

    for key in ("path", "file", "target_file", "source_path", "output_path"):
        text = _clean_text(step.get(key))
        if text and text not in group:
            group.append(text)

    targets = step.get("targets")
    if isinstance(targets, list):
        for item in targets:
            text = _clean_text(item)
            if text and text not in group:
                group.append(text)

    if not group:
        group.append(f"planner step {index + 1}")
    return group


def normalize_runtime_plan_groups(task: Dict[str, Any]) -> List[List[str]]:
    """Normalize a long engineering task into deterministic executable groups.

    Accepted sources, in priority order:
    - task["target_groups"] / task["plan_groups"] / task["groups"]
    - task["steps"] / task["planner_steps"] as one executable group per step
    - task["cycles"][*]["target_groups"] as flattened executable groups
    - task["targets"] as one group
    - task["goal"] fallback as one group

    This module intentionally does not parse or mutate source code. It prepares
    the persistent long-loop envelope and preserves planner step cardinality so
    the StepExecutor endpoint receives each planned step.
    """
    for key in ("target_groups", "plan_groups", "groups"):
        raw = task.get(key)
        if isinstance(raw, list):
            groups = [_clean_group(item) for item in raw]
            groups = [item for item in groups if item]
            if groups:
                return groups

    for key in ("steps", "planner_steps"):
        raw_steps = task.get(key)
        if isinstance(raw_steps, list):
            groups = [_step_to_runtime_group(step, index) for index, step in enumerate(raw_steps)]
            groups = [item for item in groups if item]
            if groups:
                return groups

    cycles = task.get("cycles")
    if isinstance(cycles, list):
        groups: List[List[str]] = []
        for cycle in cycles:
            if not isinstance(cycle, dict):
                continue
            raw_groups = cycle.get("target_groups") or cycle.get("plan_groups") or cycle.get("groups")
            if isinstance(raw_groups, list):
                for group in raw_groups:
                    cleaned = _clean_group(group)
                    if cleaned:
                        groups.append(cleaned)
            raw_steps = cycle.get("steps") or cycle.get("planner_steps")
            if isinstance(raw_steps, list):
                for index, step in enumerate(raw_steps):
                    cleaned = _step_to_runtime_group(step, index)
                    if cleaned:
                        groups.append(cleaned)
        if groups:
            return groups

    targets = task.get("targets")
    if isinstance(targets, list):
        group = _clean_group(targets)
        if group:
            return [group]

    goal = _clean_text(task.get("goal") or task.get("title") or task.get("task"))
    if goal:
        return [[goal]]

    return [["persistent autonomous engineering runtime"]]


def _runtime_root(repo_root: Path) -> Path:
    return repo_root / "workspace" / "long_engineering_runtime"


def _session_id(task_id: str) -> str:
    safe_task = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in _clean_text(task_id))
    if not safe_task:
        safe_task = "task"
    return f"long_runtime_{safe_task}_{uuid.uuid4().hex[:12]}"


class LongEngineeringRuntime:
    """Persistent AER long-loop envelope.

    Boundary:
    - Owns long-loop session identity, checkpoints, journal, failure marker,
      recovery resume handoff, and final continuity summary.
    - Does not own StepExecutor execution policy.
    - Does not mutate scheduler authority.
    - Does not bypass controlled mutation / confirmation layers.
    """

    def __init__(self, repo_root: Path, task: Dict[str, Any], task_id: str, goal: str) -> None:
        self.repo_root = Path(repo_root)
        self.task = task
        self.task_id = _clean_text(task_id) or _clean_text(task.get("id")) or "long_runtime_task"
        self.goal = _clean_text(goal) or _clean_text(task.get("goal")) or self.task_id
        self.session_id = _session_id(self.task_id)
        self.session_dir = _runtime_root(self.repo_root) / self.session_id
        self.checkpoints_dir = self.session_dir / "checkpoints"
        self.journal_path = self.session_dir / "session_journal.json"
        self.state_path = self.session_dir / "session_state.json"
        self.recovery_marker_path = self.session_dir / "recovery_marker.json"
        self.resume_marker_path = self.session_dir / "resume_marker.json"

    def _base_record(self, plan_groups: List[List[str]]) -> Dict[str, Any]:
        return {
            "ok": True,
            "schema": SCHEMA,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "goal": self.goal,
            "status": "running",
            "created_at": _now(),
            "updated_at": _now(),
            "plan_groups": plan_groups,
            "target_groups": plan_groups,
            "executed_groups": [],
            "checkpoints": [],
            "failures": [],
            "resume_links": [],
            "boundary": {
                "owns_persistent_long_loop_envelope": True,
                "scheduler_remains_orchestration": True,
                "step_executor_remains_execution_endpoint": True,
                "no_hidden_mutation_shortcut": True,
                "does_not_change_cli_authority": True,
            },
        }

    def _write_checkpoint(
        self,
        *,
        journal: Dict[str, Any],
        group_index: int,
        group: List[str],
        status: str,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        checkpoint = {
            "ok": canonical_runtime_status(status) == "completed",
            "schema": f"{SCHEMA}.checkpoint",
            "session_id": self.session_id,
            "task_id": self.task_id,
            "checkpoint_index": group_index,
            "group_index": group_index,
            "group": group,
            "targets": group,
            "status": status,
            "result": result,
            "created_at": _now(),
        }
        checkpoint_path = self.checkpoints_dir / f"checkpoint_{group_index:04d}_{status}.json"
        checkpoint["checkpoint_path"] = str(checkpoint_path)
        _write_json(checkpoint_path, checkpoint)

        checkpoints = journal.setdefault("checkpoints", [])
        if isinstance(checkpoints, list):
            checkpoints.append(checkpoint)
        return checkpoint

    def _write_state(self, journal: Dict[str, Any]) -> None:
        plan_groups = journal.get("plan_groups") if isinstance(journal.get("plan_groups"), list) else []
        executed_groups = journal.get("executed_groups") if isinstance(journal.get("executed_groups"), list) else []
        failures = journal.get("failures") if isinstance(journal.get("failures"), list) else []
        state = {
            "ok": bool(journal.get("ok")),
            "schema": f"{SCHEMA}.state",
            "session_id": self.session_id,
            "task_id": self.task_id,
            "goal": self.goal,
            "status": journal.get("status"),
            "plan_group_count": len(plan_groups),
            "executed_group_count": len(executed_groups),
            "failure_count": len(failures),
            "recoverable": bool(failures),
            "journal_path": str(self.journal_path),
            "recovery_marker_path": str(self.recovery_marker_path) if failures else "",
            "updated_at": _now(),
        }
        _write_json(self.state_path, state)

    def _write_journal(self, journal: Dict[str, Any]) -> None:
        journal["updated_at"] = _now()
        journal["session_dir"] = str(self.session_dir)
        journal["session_journal_path"] = str(self.journal_path)
        journal["session_state_path"] = str(self.state_path)
        _write_json(self.journal_path, journal)
        self._write_state(journal)

    def _write_recovery_marker(
        self,
        *,
        journal: Dict[str, Any],
        failed_group_index: int,
        failed_group: List[str],
        failure_result: Dict[str, Any],
        checkpoint: Dict[str, Any],
    ) -> Dict[str, Any]:
        marker = {
            "ok": True,
            "schema": f"{SCHEMA}.recovery_marker",
            "session_id": self.session_id,
            "task_id": self.task_id,
            "goal": self.goal,
            "status": "recoverable_failure",
            "failed_group_index": failed_group_index,
            "failed_plan_index": failed_group_index + 1,
            "failed_group": failed_group,
            "failed_targets": failed_group,
            "failure_result": failure_result,
            "latest_checkpoint": checkpoint,
            "journal_path": str(self.journal_path),
            "session_state_path": str(self.state_path),
            "created_at": _now(),
        }
        _write_json(self.recovery_marker_path, marker)
        journal.setdefault("failures", []).append(marker)
        return marker

    def run(
        self,
        *,
        executor: Optional[Any] = None,
        fail_group_index: int = -1,
    ) -> Dict[str, Any]:
        """Run the deterministic persistent long-loop envelope.

        executor contract:
            executor(group: list[str], group_index: int, session: LongEngineeringRuntime) -> dict

        If executor is omitted, each group is recorded as completed. This keeps the
        contract testable before wiring the full StepExecutor path.
        """
        plan_groups = normalize_runtime_plan_groups(self.task)
        journal = self._base_record(plan_groups)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

        self._write_journal(journal)

        for index, group in enumerate(plan_groups):
            if index == fail_group_index:
                result = {
                    "ok": False,
                    "status": "failed",
                    "message": "Simulated recoverable failure for long engineering runtime.",
                    "group_index": index,
                    "group": group,
                }
                checkpoint = self._write_checkpoint(
                    journal=journal,
                    group_index=index,
                    group=group,
                    status="failed",
                    result=result,
                )
                marker = self._write_recovery_marker(
                    journal=journal,
                    failed_group_index=index,
                    failed_group=group,
                    failure_result=result,
                    checkpoint=checkpoint,
                )
                journal["ok"] = False
                project_runtime_status(journal, "recoverable_failure", owner="core/runtime/long_engineering_runtime.py")
                journal["recovery_marker_path"] = str(self.recovery_marker_path)
                journal["latest_checkpoint"] = checkpoint
                journal["recovery_marker"] = marker
                self._write_journal(journal)
                return self._finalize_result(journal)

            if executor is None:
                result = {
                    "ok": True,
                    "status": "finished",
                    "message": "Recorded long engineering runtime group.",
                    "group_index": index,
                    "group": group,
                }
            else:
                raw = executor(group, index, self)
                result = raw if isinstance(raw, dict) else {"ok": False, "status": "failed", "message": str(raw)}

            status = "finished" if bool(result.get("ok")) else "failed"
            checkpoint = self._write_checkpoint(
                journal=journal,
                group_index=index,
                group=group,
                status=status,
                result=result,
            )

            if status != "finished":
                marker = self._write_recovery_marker(
                    journal=journal,
                    failed_group_index=index,
                    failed_group=group,
                    failure_result=result,
                    checkpoint=checkpoint,
                )
                journal["ok"] = False
                project_runtime_status(journal, "recoverable_failure", owner="core/runtime/long_engineering_runtime.py")
                journal["recovery_marker_path"] = str(self.recovery_marker_path)
                journal["latest_checkpoint"] = checkpoint
                journal["recovery_marker"] = marker
                self._write_journal(journal)
                return self._finalize_result(journal)

            journal.setdefault("executed_groups", []).append(
                {
                    "group_index": index,
                    "group": group,
                    "result": result,
                    "checkpoint": checkpoint,
                    "created_at": _now(),
                }
            )
            journal["latest_checkpoint"] = checkpoint
            self._write_journal(journal)

        journal["ok"] = True
        project_runtime_status(journal, "finished", owner="core/runtime/long_engineering_runtime.py")
        journal["finished_at"] = _now()
        self._write_journal(journal)
        return self._finalize_result(journal)

    def _finalize_result(self, journal: Dict[str, Any]) -> Dict[str, Any]:
        plan_groups = journal.get("plan_groups") if isinstance(journal.get("plan_groups"), list) else []
        executed_groups = journal.get("executed_groups") if isinstance(journal.get("executed_groups"), list) else []
        failures = journal.get("failures") if isinstance(journal.get("failures"), list) else []
        return {
            "ok": bool(journal.get("ok")),
            "schema": SCHEMA,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "goal": self.goal,
            "status": journal.get("status"),
            "session_dir": str(self.session_dir),
            "session_journal_path": str(self.journal_path),
            "session_state_path": str(self.state_path),
            "checkpoint_count": len(journal.get("checkpoints", [])) if isinstance(journal.get("checkpoints"), list) else 0,
            "plan_group_count": len(plan_groups),
            "executed_group_count": len(executed_groups),
            "failure_count": len(failures),
            "recoverable": bool(failures),
            "recovery_marker_path": str(self.recovery_marker_path) if failures else "",
            "latest_checkpoint": journal.get("latest_checkpoint", {}),
            "boundary": journal.get("boundary", {}),
        }


def execute_long_engineering_runtime(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    result: Optional[Dict[str, Any]] = None,
    task_id: str = "",
    goal: str = "",
    executor: Optional[Any] = None,
    fail_group_index: int = -1,
) -> Dict[str, Any]:
    current_result: Dict[str, Any] = result if isinstance(result, dict) else {}
    runtime = LongEngineeringRuntime(
        repo_root=Path(repo_root),
        task=task,
        task_id=task_id or _clean_text(task.get("id")) or _clean_text(task.get("task_id")) or "long_runtime_task",
        goal=goal or _clean_text(task.get("goal")) or _clean_text(task.get("title")),
    )
    runtime_result = runtime.run(executor=executor, fail_group_index=fail_group_index)
    current_result["long_engineering_runtime"] = runtime_result
    current_result["long_engineering_runtime_schema"] = SCHEMA
    current_result["long_engineering_runtime_ok"] = bool(runtime_result.get("ok"))
    current_result["long_engineering_runtime_status"] = runtime_result.get("status")
    current_result["long_engineering_runtime_session_id"] = runtime_result.get("session_id")
    current_result["long_engineering_runtime_journal_path"] = runtime_result.get("session_journal_path")
    current_result["long_engineering_runtime_recoverable"] = bool(runtime_result.get("recoverable"))
    current_result["ok"] = bool(runtime_result.get("ok"))
    return current_result


def find_latest_long_runtime_recovery(repo_root: Path) -> Dict[str, Any]:
    root = _runtime_root(Path(repo_root))
    if not root.exists():
        return {}

    candidates: List[Tuple[float, Dict[str, Any]]] = []
    for marker_path in root.glob("long_runtime_*/recovery_marker.json"):
        marker = _read_json(marker_path)
        if not marker:
            continue
        if marker.get("superseded_by_session_id"):
            continue
        try:
            mtime = marker_path.stat().st_mtime
        except OSError:
            mtime = 0.0
        candidates.append((mtime, marker))

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1] if candidates else {}


def resume_long_engineering_runtime(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    result: Optional[Dict[str, Any]] = None,
    task_id: str = "",
    goal: str = "",
    source_session_id: str = "",
    executor: Optional[Any] = None,
) -> Dict[str, Any]:
    """Resume a failed long runtime session from its recovery marker.

    This does not edit the source session. It creates a new linked session that
    starts from the failed group again, then records a superseded marker beside
    the original recovery marker.
    """
    repo_root = Path(repo_root)
    current_result: Dict[str, Any] = result if isinstance(result, dict) else {}
    marker: Dict[str, Any]

    if source_session_id:
        marker = _read_json(_runtime_root(repo_root) / source_session_id / "recovery_marker.json")
    else:
        marker = find_latest_long_runtime_recovery(repo_root)

    if not marker:
        resume_record = {
            "ok": False,
            "schema": f"{SCHEMA}.resume",
            "status": "no_recoverable_session",
            "reason": "no long runtime recovery marker found",
            "created_at": _now(),
        }
        current_result["long_engineering_runtime_resume"] = resume_record
        current_result["long_engineering_runtime_resume_ok"] = False
        current_result["ok"] = False
        return current_result

    source_id = _clean_text(marker.get("session_id"))
    source_journal_path = Path(_clean_text(marker.get("journal_path")))
    source_journal = _read_json(source_journal_path)
    source_groups = source_journal.get("plan_groups") if isinstance(source_journal.get("plan_groups"), list) else []
    failed_index = int(marker.get("failed_group_index") or 0)

    remaining_groups: List[List[str]] = []
    for group in source_groups[failed_index:]:
        cleaned = _clean_group(group)
        if cleaned:
            remaining_groups.append(cleaned)

    if not remaining_groups:
        failed_group = _clean_group(marker.get("failed_group"))
        if failed_group:
            remaining_groups = [failed_group]

    resumed_task = dict(task)
    resumed_task["target_groups"] = remaining_groups
    resumed_task["resumed_from_session_id"] = source_id
    resumed_task["resume_marker"] = marker

    resumed = execute_long_engineering_runtime(
        repo_root=repo_root,
        task=resumed_task,
        result={},
        task_id=f"{task_id or _clean_text(task.get('id')) or 'long_runtime_resume'}_resumed",
        goal=f"{goal or _clean_text(task.get('goal')) or 'resume long engineering runtime'} / resumed from {source_id}",
        executor=executor,
        fail_group_index=-1,
    )
    resumed_runtime = resumed.get("long_engineering_runtime", {}) if isinstance(resumed, dict) else {}
    ok = bool(resumed_runtime.get("ok"))

    superseded = dict(marker)
    superseded["superseded_by_session_id"] = resumed_runtime.get("session_id")
    superseded["superseded_by_task_id"] = task_id
    superseded["superseded_at"] = _now()
    superseded["resume_ok"] = ok

    if source_id:
        superseded_path = _runtime_root(repo_root) / source_id / "recovery_marker.superseded.json"
        _write_json(superseded_path, superseded)

    resume_record = {
        "ok": ok,
        "schema": f"{SCHEMA}.resume",
        "status": "resumed" if ok else "resume_failed",
        "source_session_id": source_id,
        "source_recovery_marker": marker,
        "remaining_groups": remaining_groups,
        "resumed_runtime": resumed_runtime,
        "resumed_session_id": resumed_runtime.get("session_id"),
        "created_at": _now(),
        "boundary": {
            "resumes_from_recovery_marker": True,
            "creates_new_linked_session": True,
            "does_not_mutate_cli_authority": True,
            "no_hidden_mutation_shortcut": True,
        },
    }
    current_result["long_engineering_runtime_resume"] = resume_record
    current_result["long_engineering_runtime_resume_ok"] = ok
    current_result["long_engineering_runtime_resume_status"] = resume_record["status"]
    current_result["long_engineering_runtime_resume_resumed_session_id"] = resumed_runtime.get("session_id")
    current_result["ok"] = ok
    return current_result


__all__ = [
    "SCHEMA",
    "LongEngineeringRuntime",
    "execute_long_engineering_runtime",
    "find_latest_long_runtime_recovery",
    "normalize_runtime_plan_groups",
    "resume_long_engineering_runtime",
]
