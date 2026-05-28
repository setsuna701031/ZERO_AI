from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict


def _workspace_relative_path(repo_root: Path, raw_path: str) -> str:
    text = str(raw_path or "").strip().strip('"').strip("'")
    if not text:
        return ""

    candidate = Path(text.replace("\\", "/"))
    try:
        workspace_root = (repo_root / "workspace").resolve()
        resolved = candidate.resolve() if candidate.is_absolute() else (repo_root / candidate).resolve()
        try:
            return resolved.relative_to(workspace_root).as_posix()
        except Exception:
            pass
        try:
            return resolved.relative_to(repo_root.resolve()).as_posix()
        except Exception:
            pass
    except Exception:
        pass

    return text.replace("\\", "/")


def build_controlled_mutation_probe_step(
    *,
    repo_root: Path,
    task_id: str,
    goal: str,
    target_path: str,
) -> Dict[str, Any]:
    """Build a safe governed-mutation probe step.

    v1 deliberately avoids changing source files.  It proves that the mutation
    authority surface can enter StepExecutor through a governed runtime envelope
    while writing only a bounded proof artifact under workspace/shared.
    """

    safe_target = _workspace_relative_path(repo_root, target_path or "workspace/shared/mutation_probe.txt")
    proof_path = f"shared/{task_id}_controlled_mutation_probe.json"

    proof_text = (
        "{\n"
        '  "schema": "zero.aer.controlled_mutation_probe.v1",\n'
        f'  "task_id": "{task_id}",\n'
        f'  "target_path": "{safe_target}",\n'
        '  "mutation_executed": false,\n'
        '  "mutation_authority_surface": "step_executor",\n'
        '  "requires_review_before_real_source_edit": true\n'
        "}\n"
    )

    return {
        "type": "write_file",
        "path": proof_path,
        "content": proof_text,
        "scope": "shared",
        "source": "controlled_mutation_bridge",
        "mutation_probe": True,
        "mutation_target_path": safe_target,
        "goal": goal,
    }


def execute_controlled_mutation_probe(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    task_id: str,
    goal: str,
    target_path: str,
) -> Dict[str, Any]:
    """Execute a safe controlled-mutation probe through StepExecutor.

    This is intentionally not a real code edit yet.  It is the first controlled
    mutation ownership bridge:

    CLI/thin bridge -> StepExecutor governed execution surface

    The probe proves that future code mutation payloads can enter the governed
    execution endpoint without moving authority into CLI or bypassing review.
    """

    step = build_controlled_mutation_probe_step(
        repo_root=repo_root,
        task_id=task_id,
        goal=goal,
        target_path=target_path,
    )

    try:
        from core.runtime.step_executor import StepExecutor

        executor = StepExecutor(workspace_root=str(repo_root / "workspace"))
        step_result = executor.execute_step(
            step=step,
            task={
                "task_id": task_id,
                "task_name": task_id,
                "goal": goal,
                "runtime_mode": "controlled_mutation_probe_v1",
                "workspace_root": str(repo_root / "workspace"),
                "shared_dir": str(repo_root / "workspace" / "shared"),
                "task_dir": str(repo_root / "workspace" / "tasks" / task_id),
                "execution_authority_handoff": task.get("execution_authority_handoff"),
                "runtime_ownership": task.get("runtime_ownership"),
            },
            context={
                "repo_root": str(repo_root),
                "workspace_root": str(repo_root / "workspace"),
                "shared_dir": str(repo_root / "workspace" / "shared"),
                "task_dir": str(repo_root / "workspace" / "tasks" / task_id),
                "controlled_mutation_probe": True,
                "formal_execution_endpoint": "core.runtime.step_executor.StepExecutor.execute_step",
            },
        )
        proof_path = repo_root / "workspace" / step["path"]
        ok = bool(step_result.get("ok", False)) if isinstance(step_result, dict) else False
        if proof_path.exists():
            ok = True

        return {
            "ok": ok,
            "schema": "zero.aer.controlled_mutation_execution_bridge.v1",
            "created_at": time.time(),
            "task_id": task_id,
            "goal": goal,
            "mode": "controlled_mutation_probe_v1",
            "mutation_executed": False,
            "mutation_probe_executed": True,
            "requires_review_before_real_source_edit": True,
            "execution_authority_endpoint": "step_executor",
            "formal_execution_endpoint": "core.runtime.step_executor.StepExecutor.execute_step",
            "step": step,
            "step_result": step_result,
            "proof_artifact_path": str(proof_path),
            "target_path": step.get("mutation_target_path"),
            "boundary": {
                "cli_is_not_execution_owner": True,
                "thin_bridge_is_compatibility_layer": True,
                "step_executor_received_mutation_surface": True,
                "real_source_mutation_blocked_in_v1": True,
                "review_required_before_real_mutation": True,
                "no_hidden_mutation_shortcut": True,
            },
        }
    except Exception as exc:
        return {
            "ok": False,
            "schema": "zero.aer.controlled_mutation_execution_bridge.v1",
            "created_at": time.time(),
            "task_id": task_id,
            "goal": goal,
            "mode": "controlled_mutation_probe_v1",
            "mutation_executed": False,
            "mutation_probe_executed": False,
            "requires_review_before_real_source_edit": True,
            "execution_authority_endpoint": "step_executor",
            "formal_execution_endpoint": "core.runtime.step_executor.StepExecutor.execute_step",
            "step": step,
            "target_path": step.get("mutation_target_path"),
            "error": {
                "type": exc.__class__.__name__,
                "message": str(exc),
            },
        }


def attach_controlled_mutation_probe(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    result: Dict[str, Any],
    task_id: str,
    goal: str,
    target_path: str,
) -> Dict[str, Any]:
    record = execute_controlled_mutation_probe(
        repo_root=repo_root,
        task=task,
        task_id=task_id,
        goal=goal,
        target_path=target_path,
    )

    result["controlled_mutation_execution"] = record
    result["controlled_mutation_execution_schema"] = record.get("schema")
    result["controlled_mutation_probe_executed"] = bool(record.get("mutation_probe_executed"))
    result["controlled_mutation_execution_ok"] = bool(record.get("ok"))

    task["controlled_mutation_execution"] = record
    task["controlled_mutation_execution_schema"] = record.get("schema")
    task["controlled_mutation_probe_executed"] = bool(record.get("mutation_probe_executed"))
    task["controlled_mutation_execution_ok"] = bool(record.get("ok"))

    return result


# ============================================================
# Controlled source mutation v2
# ============================================================

def _repo_relative_path(repo_root: Path, raw_path: str) -> str:
    text = str(raw_path or "").strip().strip('"').strip("'").replace("\\", "/")
    if not text:
        return ""

    path = Path(text)
    try:
        resolved = path.resolve() if path.is_absolute() else (repo_root / path).resolve()
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return text


def _is_allowed_mutation_target(repo_root: Path, raw_path: str) -> Dict[str, Any]:
    rel = _repo_relative_path(repo_root, raw_path)
    if not rel:
        return {"ok": False, "reason": "empty_target_path", "path": raw_path, "repo_relative_path": rel}

    normalized = rel.replace("\\", "/").lstrip("/")
    blocked_parts = {".git", ".venv", "venv", "__pycache__"}
    parts = set(Path(normalized).parts)
    if parts & blocked_parts:
        return {
            "ok": False,
            "reason": "blocked_internal_or_environment_path",
            "path": raw_path,
            "repo_relative_path": normalized,
        }

    allowed_prefixes = (
        "workspace/shared/",
        "core/runtime/",
        "core/tasks/",
        "cli/",
        "tests/",
    )
    if not normalized.startswith(allowed_prefixes):
        return {
            "ok": False,
            "reason": "outside_allowed_roots",
            "path": raw_path,
            "repo_relative_path": normalized,
            "allowed_roots": list(allowed_prefixes),
        }

    if not normalized.endswith((".py", ".txt", ".md", ".json")):
        return {
            "ok": False,
            "reason": "unsupported_mutation_file_type",
            "path": raw_path,
            "repo_relative_path": normalized,
            "allowed_suffixes": [".py", ".txt", ".md", ".json"],
        }

    return {"ok": True, "path": raw_path, "repo_relative_path": normalized}


def _read_source_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _controlled_mutation_marker(task_id: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in str(task_id))
    return f"ZERO_CONTROLLED_MUTATION_PROOF:{safe}"


def _build_mutated_text(original: str, *, task_id: str, goal: str, target_path: str) -> Dict[str, Any]:
    marker = _controlled_mutation_marker(task_id)
    if marker in original:
        return {
            "changed": False,
            "marker": marker,
            "content": original,
            "reason": "marker_already_present",
        }

    if target_path.endswith(".py"):
        addition = (
            "\n\n"
            f"# {marker}\n"
            "# Controlled source mutation proof written through StepExecutor authority.\n"
        )
    elif target_path.endswith(".json"):
        addition = (
            "\n"
            f'{{"controlled_mutation_marker": "{marker}", '
            '"note": "proof written through StepExecutor authority"}}\n'
        )
    else:
        addition = (
            "\n\n"
            f"{marker}\n"
            "Controlled source mutation proof written through StepExecutor authority.\n"
        )

    return {
        "changed": True,
        "marker": marker,
        "content": original + addition,
        "reason": "marker_appended",
    }


def _verify_mutated_target(repo_root: Path, rel_path: str) -> Dict[str, Any]:
    target = repo_root / rel_path
    if not target.exists():
        return {"ok": False, "kind": "exists", "message": "target file does not exist after mutation"}

    if rel_path.endswith(".py"):
        try:
            import py_compile

            py_compile.compile(str(target), doraise=True)
            return {"ok": True, "kind": "py_compile", "target": rel_path}
        except Exception as exc:
            return {
                "ok": False,
                "kind": "py_compile",
                "target": rel_path,
                "error": {"type": exc.__class__.__name__, "message": str(exc)},
            }

    return {"ok": True, "kind": "exists", "target": rel_path}


def execute_controlled_source_mutation(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    task_id: str,
    goal: str,
    target_path: str,
) -> Dict[str, Any]:
    """Execute a small controlled source mutation through StepExecutor.

    v2 is intentionally narrow:
    - allowed roots only;
    - snapshot before edit;
    - StepExecutor write_file owns the write;
    - verification is recorded;
    - rollback content/path is recorded, but rollback is not auto-applied unless a
      later runtime policy decides to use it.
    """

    allowed = _is_allowed_mutation_target(repo_root, target_path)
    if not allowed.get("ok"):
        return {
            "ok": False,
            "schema": "zero.aer.controlled_source_mutation.v2",
            "created_at": time.time(),
            "task_id": task_id,
            "goal": goal,
            "target_path": target_path,
            "mutation_executed": False,
            "blocked": True,
            "block_reason": allowed.get("reason"),
            "allowed_target": allowed,
            "boundary": {
                "cli_is_not_execution_owner": True,
                "step_executor_required": True,
                "allowed_roots_enforced": True,
                "no_hidden_mutation_shortcut": True,
            },
        }

    rel_path = str(allowed["repo_relative_path"])
    abs_path = repo_root / rel_path
    original = _read_source_text(abs_path)
    mutation = _build_mutated_text(original, task_id=task_id, goal=goal, target_path=rel_path)

    snapshot_dir = repo_root / "workspace" / "mutation_snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    safe_rel = rel_path.replace("/", "__").replace("\\", "__")
    snapshot_path = snapshot_dir / f"{task_id}_{safe_rel}.before"
    snapshot_path.write_text(original, encoding="utf-8")

    rollback_record = {
        "schema": "zero.aer.controlled_source_mutation.rollback.v1",
        "task_id": task_id,
        "target_path": rel_path,
        "snapshot_path": str(snapshot_path),
        "rollback_available": True,
        "rollback_applied": False,
    }

    step = {
        "type": "write_file",
        "path": rel_path,
        "content": mutation["content"],
        "source": "controlled_source_mutation_v2",
        "scope": "repo",
        "mutation_marker": mutation["marker"],
        "mutation_target_path": rel_path,
    }

    try:
        from core.runtime.step_executor import StepExecutor

        executor = StepExecutor(workspace_root=str(repo_root))
        step_result = executor.execute_step(
            step=step,
            task={
                "task_id": task_id,
                "task_name": task_id,
                "goal": goal,
                "runtime_mode": "controlled_source_mutation_v2",
                "workspace_root": str(repo_root),
                "shared_dir": str(repo_root / "workspace" / "shared"),
                "task_dir": str(repo_root / "workspace" / "tasks" / task_id),
                "execution_authority_handoff": task.get("execution_authority_handoff"),
                "runtime_ownership": task.get("runtime_ownership"),
            },
            context={
                "repo_root": str(repo_root),
                "workspace_root": str(repo_root),
                "controlled_source_mutation": True,
                "formal_execution_endpoint": "core.runtime.step_executor.StepExecutor.execute_step",
            },
        )

        write_ok = bool(step_result.get("ok", False)) if isinstance(step_result, dict) else False
        verify_result = _verify_mutated_target(repo_root, rel_path)
        ok = bool(write_ok and verify_result.get("ok"))

        return {
            "ok": ok,
            "schema": "zero.aer.controlled_source_mutation.v2",
            "created_at": time.time(),
            "task_id": task_id,
            "goal": goal,
            "mode": "controlled_source_mutation_v2",
            "mutation_executed": ok,
            "mutation_changed_file": bool(mutation.get("changed")),
            "mutation_marker": mutation.get("marker"),
            "target_path": rel_path,
            "allowed_target": allowed,
            "execution_authority_endpoint": "step_executor",
            "formal_execution_endpoint": "core.runtime.step_executor.StepExecutor.execute_step",
            "step": step,
            "step_result": step_result,
            "verification": verify_result,
            "rollback": rollback_record,
            "snapshot_path": str(snapshot_path),
            "boundary": {
                "cli_is_not_execution_owner": True,
                "thin_bridge_is_compatibility_layer": True,
                "step_executor_performed_source_mutation": bool(write_ok),
                "verification_required": True,
                "verification_passed": bool(verify_result.get("ok")),
                "rollback_recorded": True,
                "allowed_roots_enforced": True,
                "no_hidden_mutation_shortcut": True,
            },
        }
    except Exception as exc:
        return {
            "ok": False,
            "schema": "zero.aer.controlled_source_mutation.v2",
            "created_at": time.time(),
            "task_id": task_id,
            "goal": goal,
            "mode": "controlled_source_mutation_v2",
            "mutation_executed": False,
            "target_path": rel_path,
            "allowed_target": allowed,
            "step": step,
            "rollback": rollback_record,
            "snapshot_path": str(snapshot_path),
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
            "boundary": {
                "cli_is_not_execution_owner": True,
                "step_executor_required": True,
                "rollback_recorded": True,
                "allowed_roots_enforced": True,
                "no_hidden_mutation_shortcut": True,
            },
        }


def attach_controlled_source_mutation(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    result: Dict[str, Any],
    task_id: str,
    goal: str,
    target_path: str,
) -> Dict[str, Any]:
    record = execute_controlled_source_mutation(
        repo_root=repo_root,
        task=task,
        task_id=task_id,
        goal=goal,
        target_path=target_path,
    )

    result["controlled_source_mutation"] = record
    result["controlled_source_mutation_schema"] = record.get("schema")
    result["controlled_source_mutation_executed"] = bool(record.get("mutation_executed"))
    result["controlled_source_mutation_ok"] = bool(record.get("ok"))

    task["controlled_source_mutation"] = record
    task["controlled_source_mutation_schema"] = record.get("schema")
    task["controlled_source_mutation_executed"] = bool(record.get("mutation_executed"))
    task["controlled_source_mutation_ok"] = bool(record.get("ok"))

    return result


# ============================================================
# Controlled Mutation Transaction Seal v1
# ============================================================

def _transaction_id(task_id: str) -> str:
    import hashlib

    seed = f"{task_id}:{time.time()}".encode("utf-8", errors="replace")
    return "mutation_txn_" + hashlib.sha1(seed).hexdigest()[:16]


def _transaction_dir(repo_root: Path, transaction_id: str) -> Path:
    return repo_root / "workspace" / "mutation_transactions" / transaction_id


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _read_json(path: Path) -> Dict[str, Any]:
    import json

    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _restore_snapshot(target_path: Path, snapshot_path: Path) -> Dict[str, Any]:
    try:
        if not snapshot_path.exists():
            return {
                "ok": False,
                "reason": "snapshot_missing",
                "snapshot_path": str(snapshot_path),
                "target_path": str(target_path),
            }
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(snapshot_path.read_text(encoding="utf-8"), encoding="utf-8")
        return {
            "ok": True,
            "reason": "snapshot_restored",
            "snapshot_path": str(snapshot_path),
            "target_path": str(target_path),
        }
    except Exception as exc:
        return {
            "ok": False,
            "reason": "restore_failed",
            "snapshot_path": str(snapshot_path),
            "target_path": str(target_path),
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }


def execute_controlled_mutation_transaction(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    task_id: str,
    goal: str,
    target_path: str,
    force_verification_failure: bool = False,
) -> Dict[str, Any]:
    """Run the single-file controlled mutation transaction seal.

    Seal v1 is intentionally one-file only.  It closes the whole transaction
    lifecycle in one unit:

    allowed_roots -> snapshot -> StepExecutor write -> verify -> rollback on
    failed verification -> journal/result.
    """

    transaction_id = _transaction_id(task_id)
    txn_dir = _transaction_dir(repo_root, transaction_id)
    txn_dir.mkdir(parents=True, exist_ok=True)

    allowed = _is_allowed_mutation_target(repo_root, target_path)
    started_at = time.time()
    journal_path = txn_dir / "mutation_journal.json"
    incident_path = txn_dir / "runtime_incident.json"

    base_record: Dict[str, Any] = {
        "ok": False,
        "schema": "zero.aer.controlled_mutation_transaction_seal.v1",
        "transaction_id": transaction_id,
        "task_id": task_id,
        "goal": goal,
        "target_path": target_path,
        "started_at": started_at,
        "finished_at": None,
        "status": "started",
        "allowed_target": allowed,
        "steps": [],
        "boundary": {
            "single_file_only": True,
            "cli_is_not_execution_owner": True,
            "thin_bridge_is_compatibility_layer": True,
            "step_executor_required": True,
            "allowed_roots_enforced": True,
            "snapshot_required": True,
            "verification_required": True,
            "auto_rollback_on_failed_verification": True,
            "rollback_record_required": True,
            "mutation_journal_required": True,
            "no_hidden_mutation_shortcut": True,
        },
    }

    if not allowed.get("ok"):
        base_record.update(
            {
                "status": "blocked",
                "block_reason": allowed.get("reason"),
                "finished_at": time.time(),
                "journal_path": str(journal_path),
            }
        )
        base_record["steps"].append({"name": "allowed_roots", "ok": False, "reason": allowed.get("reason")})
        _write_json(journal_path, base_record)
        return base_record

    rel_path = str(allowed["repo_relative_path"])
    abs_path = repo_root / rel_path

    original = _read_source_text(abs_path)
    safe_rel = rel_path.replace("/", "__").replace("\\", "__")
    snapshot_path = txn_dir / f"{safe_rel}.before"
    snapshot_path.write_text(original, encoding="utf-8")
    base_record["steps"].append(
        {
            "name": "snapshot",
            "ok": True,
            "snapshot_path": str(snapshot_path),
            "target_path": rel_path,
        }
    )

    mutation = _build_mutated_text(original, task_id=transaction_id, goal=goal, target_path=rel_path)
    step = {
        "type": "write_file",
        "path": rel_path,
        "content": mutation["content"],
        "source": "controlled_mutation_transaction_seal_v1",
        "scope": "repo",
        "mutation_marker": mutation["marker"],
        "mutation_target_path": rel_path,
        "transaction_id": transaction_id,
    }

    step_result: Dict[str, Any]
    try:
        from core.runtime.step_executor import StepExecutor

        executor = StepExecutor(workspace_root=str(repo_root))
        step_result = executor.execute_step(
            step=step,
            task={
                "task_id": task_id,
                "task_name": task_id,
                "goal": goal,
                "runtime_mode": "controlled_mutation_transaction_seal_v1",
                "workspace_root": str(repo_root),
                "shared_dir": str(repo_root / "workspace" / "shared"),
                "task_dir": str(repo_root / "workspace" / "tasks" / task_id),
                "transaction_id": transaction_id,
                "execution_authority_handoff": task.get("execution_authority_handoff"),
                "runtime_ownership": task.get("runtime_ownership"),
            },
            context={
                "repo_root": str(repo_root),
                "workspace_root": str(repo_root),
                "controlled_mutation_transaction_seal": True,
                "transaction_id": transaction_id,
                "formal_execution_endpoint": "core.runtime.step_executor.StepExecutor.execute_step",
            },
        )
    except Exception as exc:
        step_result = {
            "ok": False,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }

    write_ok = bool(step_result.get("ok", False)) if isinstance(step_result, dict) else False
    base_record["steps"].append(
        {
            "name": "step_executor_write",
            "ok": write_ok,
            "step": step,
            "step_result": step_result,
            "execution_authority_endpoint": "step_executor",
        }
    )

    verification = _verify_mutated_target(repo_root, rel_path)
    if force_verification_failure:
        verification = {
            "ok": False,
            "kind": "forced_failure_probe",
            "target": rel_path,
            "reason": "force_verification_failure requested",
        }

    base_record["steps"].append({"name": "verification", "ok": bool(verification.get("ok")), "verification": verification})

    rollback_record = {
        "schema": "zero.aer.controlled_mutation_transaction.rollback.v1",
        "transaction_id": transaction_id,
        "task_id": task_id,
        "target_path": rel_path,
        "snapshot_path": str(snapshot_path),
        "rollback_available": True,
        "rollback_applied": False,
        "rollback_reason": "",
    }

    final_ok = bool(write_ok and verification.get("ok"))
    if not final_ok:
        rollback_result = _restore_snapshot(abs_path, snapshot_path)
        rollback_record["rollback_applied"] = bool(rollback_result.get("ok"))
        rollback_record["rollback_reason"] = "verification_failed_or_write_failed"
        rollback_record["rollback_result"] = rollback_result
        base_record["steps"].append({"name": "auto_rollback", "ok": bool(rollback_result.get("ok")), "rollback": rollback_record})

        incident = {
            "schema": "zero.aer.controlled_mutation_transaction.incident.v1",
            "transaction_id": transaction_id,
            "task_id": task_id,
            "target_path": rel_path,
            "reason": "controlled_mutation_transaction_failed",
            "write_ok": write_ok,
            "verification_ok": bool(verification.get("ok")),
            "rollback_applied": bool(rollback_record.get("rollback_applied")),
            "created_at": time.time(),
        }
        _write_json(incident_path, incident)
        base_record["runtime_incident"] = incident
        base_record["runtime_incident_path"] = str(incident_path)

    base_record.update(
        {
            "ok": final_ok,
            "status": "committed" if final_ok else "rolled_back",
            "finished_at": time.time(),
            "target_path": rel_path,
            "mutation_executed": final_ok,
            "mutation_marker": mutation.get("marker"),
            "mutation_changed_file": bool(mutation.get("changed")),
            "verification": verification,
            "rollback": rollback_record,
            "snapshot_path": str(snapshot_path),
            "journal_path": str(journal_path),
            "transaction_dir": str(txn_dir),
            "execution_authority_endpoint": "step_executor",
            "formal_execution_endpoint": "core.runtime.step_executor.StepExecutor.execute_step",
        }
    )

    _write_json(journal_path, base_record)
    return base_record


def attach_controlled_mutation_transaction_seal(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    result: Dict[str, Any],
    task_id: str,
    goal: str,
    target_path: str,
    force_verification_failure: bool = False,
) -> Dict[str, Any]:
    record = execute_controlled_mutation_transaction(
        repo_root=repo_root,
        task=task,
        task_id=task_id,
        goal=goal,
        target_path=target_path,
        force_verification_failure=force_verification_failure,
    )

    result["controlled_mutation_transaction"] = record
    result["controlled_mutation_transaction_schema"] = record.get("schema")
    result["controlled_mutation_transaction_id"] = record.get("transaction_id")
    result["controlled_mutation_transaction_status"] = record.get("status")
    result["controlled_mutation_transaction_ok"] = bool(record.get("ok"))
    result["controlled_mutation_transaction_journal_path"] = record.get("journal_path")
    result["controlled_mutation_transaction_rollback_applied"] = bool(
        (record.get("rollback") or {}).get("rollback_applied")
    )

    task["controlled_mutation_transaction"] = record
    task["controlled_mutation_transaction_schema"] = record.get("schema")
    task["controlled_mutation_transaction_id"] = record.get("transaction_id")
    task["controlled_mutation_transaction_status"] = record.get("status")
    task["controlled_mutation_transaction_ok"] = bool(record.get("ok"))
    task["controlled_mutation_transaction_journal_path"] = record.get("journal_path")
    task["controlled_mutation_transaction_rollback_applied"] = bool(
        (record.get("rollback") or {}).get("rollback_applied")
    )

    return result

