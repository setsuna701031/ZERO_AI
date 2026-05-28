from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from core.runtime.runtime_session import execute_persistent_runtime_session, read_json, session_root, write_json
from core.runtime.runtime_session_checkpoint import load_latest_checkpoint, list_session_checkpoints
from core.runtime.runtime_session_recovery import load_recovery_marker


def find_latest_recoverable_session(repo_root: Path) -> Dict[str, Any]:
    sessions_root = repo_root / "workspace" / "runtime_sessions"
    if not sessions_root.exists():
        return {}

    candidates: List[Dict[str, Any]] = []
    for session_dir in sorted(sessions_root.glob("runtime_session_*"), key=lambda p: p.stat().st_mtime, reverse=True):
        marker = load_recovery_marker(session_dir)
        if not marker:
            continue
        state = read_json(session_dir / "session_state.json")
        candidates.append(
            {
                "session_id": session_dir.name,
                "session_dir": str(session_dir),
                "recovery_marker": marker,
                "session_state": state,
                "mtime": session_dir.stat().st_mtime,
            }
        )

    return candidates[0] if candidates else {}


def _remaining_groups_from_original_session(session_record: Dict[str, Any], failed_plan_index: int) -> List[List[str]]:
    groups = session_record.get("target_groups")
    if not isinstance(groups, list):
        return []

    remaining: List[List[str]] = []
    # failed_plan_index is 1-based. Resume from the failed group again, then continue.
    start = max(0, int(failed_plan_index or 1) - 1)
    for group in groups[start:]:
        if isinstance(group, list):
            cleaned = [str(item).strip() for item in group if str(item).strip()]
            if cleaned:
                remaining.append(cleaned)
    return remaining


def _load_session_journal(session_dir: Path) -> Dict[str, Any]:
    return read_json(session_dir / "session_journal.json")


def execute_session_resume(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    result: Dict[str, Any],
    task_id: str,
    goal: str,
    source_session_id: str = "",
) -> Dict[str, Any]:
    """Resume a recoverable runtime session.

    Resume v1 closes one full unit:
    - locate recovery marker
    - load latest checkpoint
    - load original session journal
    - execute remaining plan groups as a new resumed session
    - append replay/resume linkage
    - write resume journal
    - mark old session recovery marker as superseded
    """

    sessions_root = repo_root / "workspace" / "runtime_sessions"
    if source_session_id:
        source_dir = sessions_root / source_session_id
        candidate = {
            "session_id": source_session_id,
            "session_dir": str(source_dir),
            "recovery_marker": load_recovery_marker(source_dir),
            "session_state": read_json(source_dir / "session_state.json"),
        }
    else:
        candidate = find_latest_recoverable_session(repo_root)

    if not candidate:
        resume_record = {
            "ok": False,
            "schema": "zero.aer.runtime_session_resume.v1",
            "task_id": task_id,
            "goal": goal,
            "status": "no_recoverable_session",
            "reason": "no recovery marker found",
            "created_at": time.time(),
        }
        result["runtime_session_resume"] = resume_record
        result["runtime_session_resume_schema"] = resume_record["schema"]
        result["runtime_session_resume_ok"] = False
        task["runtime_session_resume"] = resume_record
        return result

    source_dir = Path(str(candidate["session_dir"]))
    source_session_id = str(candidate["session_id"])
    marker = candidate.get("recovery_marker") if isinstance(candidate.get("recovery_marker"), dict) else {}
    source_state = candidate.get("session_state") if isinstance(candidate.get("session_state"), dict) else {}
    source_journal = _load_session_journal(source_dir)
    latest_checkpoint = load_latest_checkpoint(source_dir)
    all_checkpoints = list_session_checkpoints(source_dir)

    failed_plan_index = int(marker.get("failed_plan_index") or source_state.get("executed_plan_count") or 1)
    remaining_groups = _remaining_groups_from_original_session(source_journal, failed_plan_index)
    if not remaining_groups:
        # Fallback: resume the failed checkpoint targets if the original journal is incomplete.
        checkpoint_targets = latest_checkpoint.get("targets") if isinstance(latest_checkpoint.get("targets"), list) else []
        remaining_groups = [checkpoint_targets] if checkpoint_targets else []

    resume_journal_dir = repo_root / "workspace" / "runtime_session_resumes"
    resume_journal_dir.mkdir(parents=True, exist_ok=True)
    resume_journal_path = resume_journal_dir / f"{task_id}_resume_journal.json"

    if not remaining_groups:
        resume_record = {
            "ok": False,
            "schema": "zero.aer.runtime_session_resume.v1",
            "task_id": task_id,
            "goal": goal,
            "status": "no_remaining_groups",
            "source_session_id": source_session_id,
            "source_session_dir": str(source_dir),
            "recovery_marker": marker,
            "latest_checkpoint": latest_checkpoint,
            "checkpoint_count": len(all_checkpoints),
            "created_at": time.time(),
            "journal_path": str(resume_journal_path),
        }
        write_json(resume_journal_path, resume_record)
        result["runtime_session_resume"] = resume_record
        result["runtime_session_resume_schema"] = resume_record["schema"]
        result["runtime_session_resume_ok"] = False
        result["runtime_session_resume_journal_path"] = str(resume_journal_path)
        task["runtime_session_resume"] = resume_record
        return result

    resumed_result: Dict[str, Any] = {}
    resumed_task: Dict[str, Any] = dict(task)
    resumed_task["resumed_from_session_id"] = source_session_id
    resumed_task["resumed_from_checkpoint"] = latest_checkpoint.get("checkpoint_path")
    resumed_task["resume_mode"] = "runtime_session_resume_v1"

    resumed_result = execute_persistent_runtime_session(
        repo_root=repo_root,
        task=resumed_task,
        result=resumed_result,
        task_id=f"{task_id}_resumed",
        goal=f"{goal} / resumed from {source_session_id}",
        target_groups=remaining_groups,
        fail_plan_index=0,
    )
    resumed_session = resumed_result.get("persistent_runtime_session", {})
    resume_ok = bool(resumed_session.get("ok"))

    marker["superseded_by_resume_task_id"] = task_id
    marker["superseded_by_session_id"] = resumed_session.get("session_id")
    marker["superseded_at"] = time.time()
    marker["resume_ok"] = resume_ok
    write_json(source_dir / "recovery_marker.superseded.json", marker)

    resume_record = {
        "ok": resume_ok,
        "schema": "zero.aer.runtime_session_resume.v1",
        "task_id": task_id,
        "goal": goal,
        "status": "resumed" if resume_ok else "resume_failed",
        "source_session_id": source_session_id,
        "source_session_dir": str(source_dir),
        "source_recovery_marker": marker,
        "latest_checkpoint": latest_checkpoint,
        "checkpoint_count": len(all_checkpoints),
        "remaining_groups": remaining_groups,
        "resumed_session": resumed_session,
        "resumed_session_id": resumed_session.get("session_id"),
        "resumed_session_status": resumed_session.get("status"),
        "resumed_session_journal_path": resumed_session.get("session_journal_path"),
        "resume_journal_path": str(resume_journal_path),
        "created_at": time.time(),
        "boundary": {
            "resumes_from_recovery_marker": True,
            "loads_latest_checkpoint": True,
            "executes_remaining_plan_groups": True,
            "links_old_session_to_resumed_session": True,
            "does_not_mutate_cli_authority": True,
            "no_hidden_mutation_shortcut": True,
        },
    }

    write_json(resume_journal_path, resume_record)

    result["runtime_session_resume"] = resume_record
    result["runtime_session_resume_schema"] = resume_record["schema"]
    result["runtime_session_resume_ok"] = resume_ok
    result["runtime_session_resume_status"] = resume_record["status"]
    result["runtime_session_resume_journal_path"] = str(resume_journal_path)
    result["runtime_session_resume_source_session_id"] = source_session_id
    result["runtime_session_resume_resumed_session_id"] = resumed_session.get("session_id")

    task["runtime_session_resume"] = resume_record
    task["runtime_session_resume_schema"] = resume_record["schema"]
    task["runtime_session_resume_ok"] = resume_ok
    task["runtime_session_resume_status"] = resume_record["status"]
    task["runtime_session_resume_journal_path"] = str(resume_journal_path)
    task["runtime_session_resume_source_session_id"] = source_session_id
    task["runtime_session_resume_resumed_session_id"] = resumed_session.get("session_id")

    return result
