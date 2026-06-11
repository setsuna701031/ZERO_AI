from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List

from core.runtime.controlled_mutation_bridge import (
    _build_mutated_text,
    _is_allowed_mutation_target,
    _read_source_text,
    _restore_snapshot,
    _verify_mutated_target,
)


def _batch_id(task_id: str) -> str:
    seed = f"{task_id}:{time.time()}".encode("utf-8", errors="replace")
    return "engineering_batch_" + hashlib.sha1(seed).hexdigest()[:16]


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _normalize_target_list(targets: Any) -> List[str]:
    if isinstance(targets, list):
        return [str(item).strip() for item in targets if str(item).strip()]
    if isinstance(targets, str):
        return [part.strip() for part in targets.split(",") if part.strip()]
    return []


def _safe_target_name(target: str) -> str:
    return str(target).replace("\\", "/").replace("/", "__").replace(":", "_")


def _make_default_batch_targets(repo_root: Path) -> List[str]:
    shared = repo_root / "workspace" / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    targets = [
        shared / "engineering_batch_target_a.py",
        shared / "engineering_batch_target_b.py",
    ]
    for idx, target in enumerate(targets, start=1):
        if not target.exists():
            target.write_text(f'print("engineering batch target {idx}")\n', encoding="utf-8")
    return [
        "workspace/shared/engineering_batch_target_a.py",
        "workspace/shared/engineering_batch_target_b.py",
    ]


def _execute_runtime_owned_write(
    *,
    repo_root: Path,
    task_id: str,
    goal: str,
    batch_id: str,
    rel_path: str,
    content: str,
    marker: str,
    task: Dict[str, Any],
) -> Dict[str, Any]:
    step = {
        "type": "write_file",
        "path": rel_path,
        "content": content,
        "source": "governed_engineering_transaction_batch_v1",
        "scope": "repo",
        "mutation_marker": marker,
        "mutation_target_path": rel_path,
        "batch_id": batch_id,
    }

    try:
        from core.runtime.agent_execution_runtime import AgentExecutionRuntime

        runtime = AgentExecutionRuntime(workspace_root=str(repo_root))
        step_result = runtime.run_step(
            step=step,
            task={
                "task_id": task_id,
                "task_name": task_id,
                "goal": goal,
                "runtime_mode": "governed_engineering_transaction_batch_v1",
                "workspace_root": str(repo_root),
                "shared_dir": str(repo_root / "workspace" / "shared"),
                "task_dir": str(repo_root / "workspace" / "tasks" / task_id),
                "batch_id": batch_id,
                "execution_authority_handoff": task.get("execution_authority_handoff"),
                "execution_authority": task.get("execution_authority"),
                "authority_context": task.get("authority_context"),
                "runtime_authority_context": task.get("runtime_authority_context"),
                "runtime_ownership": task.get("runtime_ownership"),
            },
            context={
                "repo_root": str(repo_root),
                "workspace_root": str(repo_root),
                "governed_engineering_transaction_batch": True,
                "batch_id": batch_id,
                "formal_execution_endpoint": "AgentExecutionRuntime -> TaskRunner -> StepExecutor",
                "direct_execution": False,
                "runtime_owns_execution": True,
                "taskrunner_required": True,
                "step_executor_endpoint_only": True,
            },
        )
        return {
            "ok": bool(step_result.get("ok", False)) if isinstance(step_result, dict) else False,
            "step": step,
            "step_result": step_result,
            "direct_execution": False,
            "runtime_owns_execution": True,
            "taskrunner_required": True,
            "step_executor_endpoint_only": True,
            "authority_path": "GovernedEngineeringBatch -> AgentExecutionRuntime -> TaskRunner -> StepExecutor",
        }
    except Exception as exc:
        return {
            "ok": False,
            "step": step,
            "step_result": {
                "ok": False,
                "error": {
                    "type": exc.__class__.__name__,
                    "message": str(exc),
                },
            },
            "direct_execution": False,
            "runtime_owns_execution": True,
            "taskrunner_required": True,
            "step_executor_endpoint_only": True,
        }



def execute_governed_engineering_transaction_batch(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    task_id: str,
    goal: str,
    targets: List[str],
    force_verification_failure: bool = False,
) -> Dict[str, Any]:
    """Execute a governed multi-file engineering transaction.

    Batch v1 intentionally keeps the operation simple and deterministic:
    - multi-file target list;
    - allowed_roots check for every target before any write;
    - snapshot every target before any write;
    - AgentExecutionRuntime delegates every mutated file through TaskRunner to StepExecutor;
    - verify every target;
    - if any write/verification fails, rollback all changed targets;
    - journal + runtime incident are persisted.
    """

    if not targets:
        targets = _make_default_batch_targets(repo_root)

    batch_id = _batch_id(task_id)
    batch_dir = repo_root / "workspace" / "engineering_transactions" / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    journal_path = batch_dir / "engineering_transaction_journal.json"
    incident_path = batch_dir / "runtime_incident.json"

    started_at = time.time()
    allowed_records: List[Dict[str, Any]] = []
    for target in targets:
        allowed_records.append(_is_allowed_mutation_target(repo_root, target))

    blocked = [record for record in allowed_records if not record.get("ok")]
    base: Dict[str, Any] = {
        "ok": False,
        "schema": "zero.aer.governed_engineering_transaction_batch.v1",
        "batch_id": batch_id,
        "task_id": task_id,
        "goal": goal,
        "started_at": started_at,
        "finished_at": None,
        "status": "started",
        "target_count": len(targets),
        "targets": targets,
        "allowed_targets": allowed_records,
        "steps": [],
        "boundary": {
            "multi_file_batch": True,
            "cli_is_not_execution_owner": True,
            "thin_bridge_is_compatibility_layer": True,
            "step_executor_required": True,
            "allowed_roots_enforced": True,
            "batch_snapshot_required": True,
            "batch_verification_required": True,
            "auto_rollback_on_any_failure": True,
            "journal_required": True,
            "runtime_incident_on_failure": True,
            "no_hidden_mutation_shortcut": True,
        },
    }

    if blocked:
        base.update(
            {
                "status": "blocked",
                "block_reason": "one_or_more_targets_outside_allowed_roots",
                "blocked_targets": blocked,
                "finished_at": time.time(),
                "journal_path": str(journal_path),
            }
        )
        base["steps"].append({"name": "allowed_roots", "ok": False, "blocked_targets": blocked})
        _write_json(journal_path, base)
        return base

    rel_paths = [str(record["repo_relative_path"]) for record in allowed_records]
    snapshots: List[Dict[str, Any]] = []
    for rel_path in rel_paths:
        abs_path = repo_root / rel_path
        original = _read_source_text(abs_path)
        snapshot_path = batch_dir / f"{_safe_target_name(rel_path)}.before"
        snapshot_path.write_text(original, encoding="utf-8")
        snapshots.append(
            {
                "target_path": rel_path,
                "snapshot_path": str(snapshot_path),
                "original_size": len(original),
            }
        )
    base["steps"].append({"name": "batch_snapshot", "ok": True, "snapshots": snapshots})

    write_records: List[Dict[str, Any]] = []
    for rel_path in rel_paths:
        original = _read_source_text(repo_root / rel_path)
        mutation = _build_mutated_text(original, task_id=f"{batch_id}_{_safe_target_name(rel_path)}", goal=goal, target_path=rel_path)
        write_record = _execute_runtime_owned_write(
            repo_root=repo_root,
            task_id=task_id,
            goal=goal,
            batch_id=batch_id,
            rel_path=rel_path,
            content=mutation["content"],
            marker=str(mutation.get("marker") or ""),
            task=task,
        )
        write_record["target_path"] = rel_path
        write_record["mutation_marker"] = mutation.get("marker")
        write_record["mutation_changed_file"] = bool(mutation.get("changed"))
        write_records.append(write_record)

    write_ok = all(bool(record.get("ok")) for record in write_records)
    base["steps"].append({"name": "step_executor_batch_write", "ok": write_ok, "writes": write_records})

    verification_records: List[Dict[str, Any]] = []
    for rel_path in rel_paths:
        verify = _verify_mutated_target(repo_root, rel_path)
        verification_records.append(verify)

    if force_verification_failure:
        verification_records.append(
            {
                "ok": False,
                "kind": "forced_failure_probe",
                "target": ",".join(rel_paths),
                "reason": "force_verification_failure requested",
            }
        )

    verification_ok = all(bool(record.get("ok")) for record in verification_records)
    base["steps"].append({"name": "batch_verification", "ok": verification_ok, "verification": verification_records})

    rollback_records: List[Dict[str, Any]] = []
    final_ok = bool(write_ok and verification_ok)

    if not final_ok:
        for snapshot in snapshots:
            target_path = repo_root / str(snapshot["target_path"])
            snapshot_path = Path(str(snapshot["snapshot_path"]))
            rollback_result = _restore_snapshot(target_path, snapshot_path)
            rollback_records.append(
                {
                    "target_path": str(snapshot["target_path"]),
                    "snapshot_path": str(snapshot_path),
                    "rollback_result": rollback_result,
                    "rollback_applied": bool(rollback_result.get("ok")),
                }
            )

        incident = {
            "schema": "zero.aer.governed_engineering_transaction_batch.incident.v1",
            "batch_id": batch_id,
            "task_id": task_id,
            "reason": "governed_engineering_transaction_batch_failed",
            "write_ok": write_ok,
            "verification_ok": verification_ok,
            "rollback_applied_count": sum(1 for item in rollback_records if item.get("rollback_applied")),
            "created_at": time.time(),
        }
        _write_json(incident_path, incident)
        base["runtime_incident"] = incident
        base["runtime_incident_path"] = str(incident_path)
        base["steps"].append({"name": "batch_auto_rollback", "ok": all(item.get("rollback_applied") for item in rollback_records), "rollback": rollback_records})

    base.update(
        {
            "ok": final_ok,
            "status": "committed" if final_ok else "rolled_back",
            "finished_at": time.time(),
            "batch_id": batch_id,
            "target_paths": rel_paths,
            "mutation_executed": final_ok,
            "write_ok": write_ok,
            "verification_ok": verification_ok,
            "verification": verification_records,
            "snapshots": snapshots,
            "rollback": {
                "schema": "zero.aer.governed_engineering_transaction_batch.rollback.v1",
                "batch_id": batch_id,
                "rollback_available": True,
                "rollback_applied": bool(rollback_records),
                "rollback_records": rollback_records,
            },
            "journal_path": str(journal_path),
            "transaction_dir": str(batch_dir),
            "execution_authority_endpoint": "runtime_owner",
            "formal_execution_endpoint": "AgentExecutionRuntime -> TaskRunner -> StepExecutor",
        }
    )

    _write_json(journal_path, base)
    return base


def attach_governed_engineering_transaction_batch(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    result: Dict[str, Any],
    task_id: str,
    goal: str,
    targets: List[str],
    force_verification_failure: bool = False,
) -> Dict[str, Any]:
    record = execute_governed_engineering_transaction_batch(
        repo_root=repo_root,
        task=task,
        task_id=task_id,
        goal=goal,
        targets=targets,
        force_verification_failure=force_verification_failure,
    )

    result["governed_engineering_transaction_batch"] = record
    result["governed_engineering_transaction_batch_schema"] = record.get("schema")
    result["governed_engineering_transaction_batch_id"] = record.get("batch_id")
    result["governed_engineering_transaction_batch_status"] = record.get("status")
    result["governed_engineering_transaction_batch_ok"] = bool(record.get("ok"))
    result["governed_engineering_transaction_batch_journal_path"] = record.get("journal_path")
    result["governed_engineering_transaction_batch_rollback_applied"] = bool(
        (record.get("rollback") or {}).get("rollback_applied")
    )

    task["governed_engineering_transaction_batch"] = record
    task["governed_engineering_transaction_batch_schema"] = record.get("schema")
    task["governed_engineering_transaction_batch_id"] = record.get("batch_id")
    task["governed_engineering_transaction_batch_status"] = record.get("status")
    task["governed_engineering_transaction_batch_ok"] = bool(record.get("ok"))
    task["governed_engineering_transaction_batch_journal_path"] = record.get("journal_path")
    task["governed_engineering_transaction_batch_rollback_applied"] = bool(
        (record.get("rollback") or {}).get("rollback_applied")
    )

    return result
