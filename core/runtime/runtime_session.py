from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List

from core.runtime.runtime_plan_executor import execute_runtime_mutation_plan_graph


def new_runtime_session_id(task_id: str) -> str:
    seed = f"{task_id}:{time.time()}".encode("utf-8", errors="replace")
    return "runtime_session_" + hashlib.sha1(seed).hexdigest()[:16]


def session_root(repo_root: Path, session_id: str) -> Path:
    return repo_root / "workspace" / "runtime_sessions" / session_id


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def default_session_targets(repo_root: Path) -> List[List[str]]:
    shared = repo_root / "workspace" / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    target_sets = [
        [
            "workspace/shared/runtime_session_plan_a1.py",
            "workspace/shared/runtime_session_plan_a2.py",
        ],
        [
            "workspace/shared/runtime_session_plan_b1.py",
            "workspace/shared/runtime_session_plan_b2.py",
        ],
    ]
    counter = 1
    for group in target_sets:
        for target_text in group:
            target = repo_root / target_text
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f'print("runtime session target {counter}")\n', encoding="utf-8")
            counter += 1
    return target_sets


def parse_session_targets(raw_targets: Any, repo_root: Path) -> List[List[str]]:
    if isinstance(raw_targets, list):
        if raw_targets and all(isinstance(item, list) for item in raw_targets):
            return [[str(part).strip() for part in item if str(part).strip()] for item in raw_targets]
        values = [str(item).strip() for item in raw_targets if str(item).strip()]
        if values:
            return [values]
    if isinstance(raw_targets, str) and raw_targets.strip():
        # Use semicolon to separate plan groups, comma to separate files in a group.
        groups: List[List[str]] = []
        for group_text in raw_targets.split(";"):
            group = [part.strip() for part in group_text.split(",") if part.strip()]
            if group:
                groups.append(group)
        if groups:
            return groups
    return default_session_targets(repo_root)


def execute_persistent_runtime_session(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    result: Dict[str, Any],
    task_id: str,
    goal: str,
    target_groups: List[List[str]],
    fail_plan_index: int = 0,
) -> Dict[str, Any]:
    """Execute a persistent multi-plan runtime session.

    Session v1 is a complete session unit:
    - session id
    - multiple Runtime Mutation Plan Graph executions
    - checkpoint after each plan
    - replay journal
    - session state
    - failure recovery marker
    - runtime result linkage
    """

    session_id = new_runtime_session_id(task_id)
    root = session_root(repo_root, session_id)
    checkpoints_dir = root / "checkpoints"
    replay_path = root / "session_replay.json"
    state_path = root / "session_state.json"
    journal_path = root / "session_journal.json"
    incident_path = root / "runtime_incident.json"
    root.mkdir(parents=True, exist_ok=True)
    checkpoints_dir.mkdir(parents=True, exist_ok=True)

    session_started_at = time.time()
    replay_events: List[Dict[str, Any]] = []
    plan_records: List[Dict[str, Any]] = []
    checkpoints: List[Dict[str, Any]] = []
    status = "running"
    ok = True
    recovery_marker: Dict[str, Any] = {}

    for index, targets in enumerate(target_groups, start=1):
        plan_task_id = f"{task_id}_plan_{index}"
        force_failure = bool(fail_plan_index and index == fail_plan_index)

        replay_events.append(
            {
                "event": "plan_started",
                "session_id": session_id,
                "plan_index": index,
                "plan_task_id": plan_task_id,
                "targets": targets,
                "force_verification_failure": force_failure,
                "created_at": time.time(),
            }
        )

        intermediate_result: Dict[str, Any] = {}
        intermediate_task: Dict[str, Any] = dict(task)
        plan_result = execute_runtime_mutation_plan_graph(
            repo_root=repo_root,
            task=intermediate_task,
            result=intermediate_result,
            task_id=plan_task_id,
            goal=f"{goal} / plan {index}",
            targets=targets,
            force_verification_failure=force_failure,
        )
        plan_record = plan_result.get("runtime_mutation_plan_graph", {})
        plan_ok = bool(plan_record.get("ok"))
        plan_records.append(plan_record)

        checkpoint = {
            "schema": "zero.aer.runtime_session_checkpoint.v1",
            "session_id": session_id,
            "task_id": task_id,
            "plan_index": index,
            "plan_task_id": plan_task_id,
            "plan_id": plan_record.get("plan_id"),
            "plan_status": plan_record.get("status"),
            "plan_ok": plan_ok,
            "rollback_applied": bool(plan_record.get("rollback_applied")),
            "created_at": time.time(),
            "targets": targets,
            "journal_path": plan_record.get("journal_path"),
        }
        checkpoint_path = checkpoints_dir / f"checkpoint_{index:03d}.json"
        write_json(checkpoint_path, checkpoint)
        checkpoint["checkpoint_path"] = str(checkpoint_path)
        checkpoints.append(checkpoint)

        replay_events.append(
            {
                "event": "plan_finished",
                "session_id": session_id,
                "plan_index": index,
                "plan_task_id": plan_task_id,
                "plan_id": plan_record.get("plan_id"),
                "plan_status": plan_record.get("status"),
                "plan_ok": plan_ok,
                "rollback_applied": bool(plan_record.get("rollback_applied")),
                "checkpoint_path": str(checkpoint_path),
                "created_at": time.time(),
            }
        )

        if not plan_ok:
            ok = False
            status = "recovery_required"
            recovery_marker = {
                "schema": "zero.aer.runtime_session_recovery_marker.v1",
                "session_id": session_id,
                "failed_plan_index": index,
                "failed_plan_task_id": plan_task_id,
                "failed_plan_id": plan_record.get("plan_id"),
                "recovery_reason": "runtime_plan_failed",
                "rollback_applied": bool(plan_record.get("rollback_applied")),
                "resume_from_checkpoint": str(checkpoint_path),
                "created_at": time.time(),
            }
            write_json(root / "recovery_marker.json", recovery_marker)
            break

    if ok:
        status = "completed"

    session_finished_at = time.time()
    session_state = {
        "schema": "zero.aer.persistent_runtime_session.state.v1",
        "session_id": session_id,
        "task_id": task_id,
        "goal": goal,
        "status": status,
        "ok": ok,
        "started_at": session_started_at,
        "finished_at": session_finished_at,
        "plan_count": len(target_groups),
        "executed_plan_count": len(plan_records),
        "checkpoint_count": len(checkpoints),
        "last_checkpoint_path": checkpoints[-1]["checkpoint_path"] if checkpoints else "",
        "recovery_marker_path": str(root / "recovery_marker.json") if recovery_marker else "",
    }
    replay_payload = {
        "schema": "zero.aer.persistent_runtime_session.replay.v1",
        "session_id": session_id,
        "task_id": task_id,
        "events": replay_events,
        "created_at": session_started_at,
        "updated_at": session_finished_at,
    }
    session_record = {
        "ok": ok,
        "schema": "zero.aer.persistent_runtime_session.v1",
        "session_id": session_id,
        "task_id": task_id,
        "goal": goal,
        "status": status,
        "started_at": session_started_at,
        "finished_at": session_finished_at,
        "target_groups": target_groups,
        "plan_records": plan_records,
        "checkpoints": checkpoints,
        "replay_journal_path": str(replay_path),
        "session_state_path": str(state_path),
        "session_journal_path": str(journal_path),
        "session_dir": str(root),
        "recovery_marker": recovery_marker,
        "recovery_marker_path": str(root / "recovery_marker.json") if recovery_marker else "",
        "runtime_result_linkage": {
            "task_id": task_id,
            "plan_ids": [record.get("plan_id") for record in plan_records],
            "plan_journals": [record.get("journal_path") for record in plan_records],
            "checkpoints": [checkpoint.get("checkpoint_path") for checkpoint in checkpoints],
        },
        "boundary": {
            "multi_plan_session": True,
            "checkpoint_after_each_plan": True,
            "replay_journal_recorded": True,
            "session_state_recorded": True,
            "failure_recovery_marker_recorded": bool(recovery_marker),
            "runtime_plan_graph_execution_used": True,
            "cli_is_not_execution_owner": True,
            "thin_bridge_is_compatibility_layer": True,
            "no_hidden_mutation_shortcut": True,
        },
    }

    write_json(state_path, session_state)
    write_json(replay_path, replay_payload)
    write_json(journal_path, session_record)

    if recovery_marker:
        incident = {
            "schema": "zero.aer.persistent_runtime_session.incident.v1",
            "session_id": session_id,
            "task_id": task_id,
            "reason": "runtime_session_recovery_required",
            "status": status,
            "recovery_marker_path": str(root / "recovery_marker.json"),
            "created_at": time.time(),
        }
        write_json(incident_path, incident)
        session_record["runtime_incident"] = incident
        session_record["runtime_incident_path"] = str(incident_path)
        write_json(journal_path, session_record)

    result["persistent_runtime_session"] = session_record
    result["persistent_runtime_session_schema"] = session_record["schema"]
    result["persistent_runtime_session_id"] = session_id
    result["persistent_runtime_session_status"] = status
    result["persistent_runtime_session_ok"] = ok
    result["persistent_runtime_session_journal_path"] = str(journal_path)
    result["persistent_runtime_session_state_path"] = str(state_path)
    result["persistent_runtime_session_replay_path"] = str(replay_path)
    result["persistent_runtime_session_recovery_marker_path"] = session_record.get("recovery_marker_path", "")

    task["persistent_runtime_session"] = session_record
    task["persistent_runtime_session_schema"] = session_record["schema"]
    task["persistent_runtime_session_id"] = session_id
    task["persistent_runtime_session_status"] = status
    task["persistent_runtime_session_ok"] = ok
    task["persistent_runtime_session_journal_path"] = str(journal_path)
    task["persistent_runtime_session_state_path"] = str(state_path)
    task["persistent_runtime_session_replay_path"] = str(replay_path)
    task["persistent_runtime_session_recovery_marker_path"] = session_record.get("recovery_marker_path", "")

    return result
