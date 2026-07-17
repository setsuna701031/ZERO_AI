from __future__ import annotations

from core.runtime.runtime_status_canonicalization import canonical_runtime_status
from core.runtime.task_runtime import project_runtime_status
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.artifacts.registry import update_artifact_graph, write_json_file
from core.runtime.aer_runtime_ownership_bridge import attach_runtime_ownership_record, summarize_runtime_ownership_transition
from core.runtime.execution_authority_handoff import attach_execution_authority_handoff_record
from core.runtime.artifact_step_bridge import attach_step_executor_artifact_execution
from core.runtime.controlled_mutation_bridge import attach_controlled_mutation_probe, attach_controlled_source_mutation, attach_controlled_mutation_transaction_seal
from core.runtime.governed_engineering_batch import attach_governed_engineering_transaction_batch, _make_default_batch_targets, _normalize_target_list
from core.runtime.runtime_plan_executor import execute_runtime_mutation_plan_graph
from core.runtime.runtime_session import execute_persistent_runtime_session, parse_session_targets
from core.runtime.runtime_session_resume import execute_session_resume
from core.runtime.runtime_session_recovery_finalization import finalize_runtime_session_recovery
from core.runtime.runtime_supervisor import run_runtime_supervisor
from core.artifacts.writers import (
    build_generic_ingestion_artifact,
    build_markdown_report_artifact,
    build_python_hello_world_artifact,
    build_summary_artifact,
    build_system_analysis_artifact,
)
from core.tasks.task_index import (
    deps_satisfied,
    read_tasks_index,
    shared_dir,
    task_goal,
    task_id,
    task_status,
    tasks_dir,
    write_tasks_index,
)


def task_dir(repo_root: Path, task_name: str) -> Path:
    return tasks_dir(repo_root) / task_name


def is_fast_routable_task(task: Dict[str, Any]) -> bool:
    task_type = str(task.get("type") or "").strip().lower()
    goal = task_goal(task).lower()
    routable_goal = any(
        marker in goal
        for marker in (
            "hello world",
            "summarize",
            "summary",
            "markdown report",
            "report.md",
            "generate a markdown",
            "create a markdown",
            "目前系統",
            "system",
            "controlled mutation",
            "governed mutation",
            "mutation probe",
            "controlled source mutation",
            "source mutation",
            "controlled mutation transaction",
            "mutation transaction",
            "transaction seal",
            "governed engineering transaction batch",
            "engineering transaction batch",
            "multi-file transaction",
            "transaction batch",
            "runtime mutation plan graph",
            "mutation plan graph",
            "plan graph",
            "persistent runtime session",
            "runtime session",
            "long-chain session",
            "runtime session resume",
            "resume runtime session",
            "session resume",
            "runtime session recovery finalization",
            "recovery finalization",
            "finalize runtime session recovery",
            "runtime supervisor",
            "autonomous runtime supervisor",
            "runtime watchdog",
            "scheduler",
            "scheduler status",
        )
    )
    return task_type in {"ask", "chat", "summarize", "report", "markdown_report", "scheduler"} or routable_goal


def _load_task_plan_payload(repo_root: Path, task: Dict[str, Any]) -> Dict[str, Any]:
    current_task_id = task_id(task)
    candidates: List[Path] = []

    for key in ("plan_path", "plan_file"):
        raw = str(task.get(key) or "").strip()
        if raw:
            path = Path(raw)
            candidates.append(path if path.is_absolute() else repo_root / path)

    if current_task_id:
        candidates.append(task_dir(repo_root, current_task_id) / "plan.json")

    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload

    return {}


def _extract_steps_from_plan_payload(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    for key in ("steps", "plan", "actions"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    planner_result = payload.get("planner_result")
    if isinstance(planner_result, dict):
        for key in ("steps", "plan", "actions"):
            value = planner_result.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

    return []


def _planner_contract_output_path(repo_root: Path, task: Dict[str, Any]) -> str:
    step_sources: List[Any] = []
    for key in ("steps", "plan", "actions"):
        value = task.get(key)
        if isinstance(value, list):
            step_sources.extend(value)

    plan_payload = _load_task_plan_payload(repo_root, task)
    step_sources.extend(_extract_steps_from_plan_payload(plan_payload))

    for step in reversed(step_sources):
        if not isinstance(step, dict):
            continue
        step_type = str(step.get("type") or step.get("action") or "").strip().lower()
        if step_type not in {"write_file", "append_file", "workspace_write", "workspace_append"}:
            continue
        raw_path = str(
            step.get("path")
            or step.get("target_path")
            or step.get("file_path")
            or step.get("target")
            or ""
        ).strip()
        if raw_path:
            return raw_path

    return ""


def _with_planner_contract_output(repo_root: Path, task: Dict[str, Any], artifact: Dict[str, Any]) -> Dict[str, Any]:
    output_path = _planner_contract_output_path(repo_root, task)
    if not output_path or not isinstance(artifact, dict):
        return artifact

    updated = dict(artifact)
    updated["planner_contract_output_path"] = output_path
    # If the thin writer already wrote to a fallback path, preserve the contract
    # by rewriting through the same StepExecutor artifact bridge destination.
    # The bridge will receive artifact_path and write content_preview there.
    path = Path(output_path)
    resolved = path if path.is_absolute() else repo_root / path
    updated["artifact_path"] = str(resolved)
    return updated


def select_artifact_writer(repo_root: Path, task: Dict[str, Any]) -> Dict[str, Any]:
    current_task_id = task_id(task)
    task_type = str(task.get("type") or "").strip().lower()
    goal = task_goal(task)
    lowered = goal.lower()
    current_shared_dir = shared_dir(repo_root)

    if ("markdown" in lowered or ".md" in lowered or "report" in lowered) and (
        "generate" in lowered
        or "create" in lowered
        or "建立" in goal
        or "產生" in goal
        or "report" in lowered
    ):
        output_path = _planner_contract_output_path(repo_root, task)
        return build_markdown_report_artifact(repo_root, current_shared_dir, goal, output_path=output_path or None)

    if task_type == "summarize" or "summarize" in lowered or "summary" in lowered or "摘要" in goal:
        output_path = _planner_contract_output_path(repo_root, task)
        return build_summary_artifact(repo_root, current_shared_dir, goal, output_path=output_path or None)

    if "hello world" in lowered and ("python" in lowered or "py" in lowered):
        return build_python_hello_world_artifact(repo_root, current_shared_dir, current_task_id)

    if "分析" in goal or "system" in lowered or "目前系統" in goal:
        tasks = read_tasks_index(repo_root)
        queued = sum(1 for item in tasks if task_status(item) == "queued")
        finished = sum(1 for item in tasks if canonical_runtime_status(task_status(item)) == "completed")
        failed = sum(1 for item in tasks if task_status(item) == "failed")
        return build_system_analysis_artifact(
            repo_root=repo_root,
            shared_dir=current_shared_dir,
            task_id=current_task_id,
            total_tasks=len(tasks),
            queued=queued,
            finished=finished,
            failed=failed,
        )

    return build_generic_ingestion_artifact(current_shared_dir, current_task_id, task_type, goal)


def execute_ingestion_task(repo_root: Path, task: Dict[str, Any]) -> Dict[str, Any]:
    task_type = str(task.get("type") or "").strip().lower()
    goal = task_goal(task)
    current_task_id = task_id(task)
    current_shared_dir = shared_dir(repo_root)

    artifact = select_artifact_writer(repo_root, task)
    graph_path = update_artifact_graph(
        repo_root=repo_root,
        shared_dir=current_shared_dir,
        task_id=current_task_id,
        goal=goal,
        artifact=artifact,
    )

    result = {
        "ok": bool(artifact.get("ok", False)),
        "task_id": current_task_id,
        "type": task_type,
        "goal": goal,
        "runtime_mode": "thin_execution_bridge_v1",
        "planner_attached": False,
        "executor_attached": "thin_artifact_writer",
        "artifact": artifact,
        "artifact_graph_path": str(graph_path),
        "message": f"Thin execution bridge handled task: {goal}",
    }
    result = attach_runtime_ownership_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=current_task_id,
        goal=goal,
        runtime_mode="thin_execution_bridge_v1",
    )
    result["runtime_ownership_transition"] = summarize_runtime_ownership_transition(
        result.get("runtime_ownership", {})
    )
    result = attach_execution_authority_handoff_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=current_task_id,
        goal=goal,
    )
    result = attach_step_executor_artifact_execution(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=current_task_id,
        goal=goal,
    )

    current_task_dir = task_dir(repo_root, current_task_id)
    result_path = current_task_dir / "result.json"
    snapshot_path = current_task_dir / "task_snapshot.json"
    runtime_state_path = current_task_dir / "runtime_state.json"

    task["result_path"] = str(result_path)
    task["snapshot_path"] = str(snapshot_path)
    task["runtime_state_path"] = str(runtime_state_path)
    task["artifact_path"] = artifact.get("artifact_path")
    task["artifact_graph_path"] = str(graph_path)

    write_json_file(result_path, result)
    write_json_file(snapshot_path, task)
    write_json_file(
        runtime_state_path,
        {
            "ok": True,
            "task_id": current_task_id,
            "status": "finished",
            "runtime_mode": "thin_execution_bridge_v1",
            "artifact_path": artifact.get("artifact_path"),
            "artifact_graph_path": str(graph_path),
            "result_path": str(result_path),
            "runtime_ownership": result.get("runtime_ownership"),
            "runtime_ownership_schema": result.get("runtime_ownership_schema"),
            "runtime_ownership_transition": result.get("runtime_ownership_transition"),
            "formal_execution_endpoint": result.get("formal_execution_endpoint"),
            "execution_authority_handoff": result.get("execution_authority_handoff"),
            "execution_authority_handoff_schema": result.get("execution_authority_handoff_schema"),
            "authority_handoff_status": result.get("authority_handoff_status"),
            "step_executor_artifact_execution": result.get("step_executor_artifact_execution"),
            "step_executor_artifact_execution_schema": result.get("step_executor_artifact_execution_schema"),
            "step_executor_handoff_executed": result.get("step_executor_handoff_executed"),
            "step_executor_artifact_execution_ok": result.get("step_executor_artifact_execution_ok"),
        },
    )

    return result



def is_controlled_mutation_probe_task(task: Dict[str, Any]) -> bool:
    task_type = str(task.get("type") or task.get("task_type") or "").strip().lower()
    goal = task_goal(task).lower()
    return (
        task_type in {"controlled_mutation", "governed_mutation", "mutation_probe"}
        or "controlled mutation" in goal
        or "governed mutation" in goal
        or "mutation probe" in goal
        or "controlled code mutation" in goal
    )


def _extract_mutation_target_from_goal(goal: str) -> str:
    import re

    text = str(goal or "")
    for pattern in (
        r"(?:for|target|path|file)\s+([A-Za-z0-9_./\\-]+\.py)",
        r"([A-Za-z0-9_./\\-]+\.py)",
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return str(match.group(1)).strip()
    return "workspace/shared/mutation_probe.txt"



def is_controlled_source_mutation_task(task: Dict[str, Any]) -> bool:
    task_type = str(task.get("type") or task.get("task_type") or "").strip().lower()
    goal = task_goal(task).lower()
    return (
        task_type in {"controlled_source_mutation", "source_mutation", "governed_source_mutation"}
        or "controlled source mutation" in goal
        or "source mutation" in goal
        or "real source mutation" in goal
    )



def execute_controlled_mutation_task(repo_root: Path, task: Dict[str, Any]) -> Dict[str, Any]:
    task_type = str(task.get("type") or "").strip().lower() or "controlled_mutation"
    goal = task_goal(task)
    current_task_id = task_id(task)
    target_path = str(task.get("target_path") or task.get("path") or "").strip()
    if not target_path:
        target_path = _extract_mutation_target_from_goal(goal)

    artifact = {
        "ok": True,
        "artifact_type": "controlled_mutation_probe",
        "artifact_path": str(shared_dir(repo_root) / f"{current_task_id}_controlled_mutation_probe.json"),
        "input_path": target_path,
        "content_preview": "",
        "message": "Prepared controlled mutation probe.",
    }

    graph_path = update_artifact_graph(
        repo_root=repo_root,
        shared_dir=shared_dir(repo_root),
        task_id=current_task_id,
        goal=goal,
        artifact=artifact,
    )

    result = {
        "ok": True,
        "task_id": current_task_id,
        "type": task_type,
        "goal": goal,
        "runtime_mode": "controlled_mutation_probe_v1",
        "planner_attached": False,
        "executor_attached": "step_executor_controlled_mutation_probe",
        "artifact": artifact,
        "artifact_graph_path": str(graph_path),
        "message": f"Controlled mutation probe handled task: {goal}",
    }

    result = attach_runtime_ownership_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=current_task_id,
        goal=goal,
        runtime_mode="controlled_mutation_probe_v1",
    )
    result["runtime_ownership_transition"] = summarize_runtime_ownership_transition(
        result.get("runtime_ownership", {})
    )
    result = attach_execution_authority_handoff_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=current_task_id,
        goal=goal,
    )
    result = attach_controlled_mutation_probe(
        repo_root=repo_root,
        task=task,
        result=result,
        task_id=current_task_id,
        goal=goal,
        target_path=target_path,
    )
    result["ok"] = bool(result.get("controlled_mutation_execution_ok"))

    current_task_dir = task_dir(repo_root, current_task_id)
    result_path = current_task_dir / "result.json"
    snapshot_path = current_task_dir / "task_snapshot.json"
    runtime_state_path = current_task_dir / "runtime_state.json"

    task["result_path"] = str(result_path)
    task["snapshot_path"] = str(snapshot_path)
    task["runtime_state_path"] = str(runtime_state_path)
    task["artifact_path"] = artifact.get("artifact_path")
    task["artifact_graph_path"] = str(graph_path)

    write_json_file(result_path, result)
    write_json_file(snapshot_path, task)
    write_json_file(
        runtime_state_path,
        {
            "ok": bool(result.get("ok")),
            "task_id": current_task_id,
            "status": "finished" if result.get("ok") else "failed",
            "runtime_mode": "controlled_mutation_probe_v1",
            "artifact_path": artifact.get("artifact_path"),
            "artifact_graph_path": str(graph_path),
            "result_path": str(result_path),
            "runtime_ownership": result.get("runtime_ownership"),
            "execution_authority_handoff": result.get("execution_authority_handoff"),
            "controlled_mutation_execution": result.get("controlled_mutation_execution"),
            "controlled_mutation_execution_schema": result.get("controlled_mutation_execution_schema"),
            "controlled_mutation_execution_ok": result.get("controlled_mutation_execution_ok"),
        },
    )

    return result



def is_controlled_mutation_transaction_task(task: Dict[str, Any]) -> bool:
    task_type = str(task.get("type") or task.get("task_type") or "").strip().lower()
    goal = task_goal(task).lower()
    return (
        task_type in {"controlled_mutation_transaction", "mutation_transaction", "transaction_mutation"}
        or "controlled mutation transaction" in goal
        or "mutation transaction" in goal
        or "transaction seal" in goal
    )



def is_governed_engineering_batch_task(task: Dict[str, Any]) -> bool:
    task_type = str(task.get("type") or task.get("task_type") or "").strip().lower()
    goal = task_goal(task).lower()
    return (
        task_type in {"governed_engineering_batch", "engineering_batch", "transaction_batch", "multi_file_transaction"}
        or "governed engineering transaction batch" in goal
        or "engineering transaction batch" in goal
        or "multi-file transaction" in goal
        or "transaction batch" in goal
    )



def is_runtime_mutation_plan_task(task: Dict[str, Any]) -> bool:
    task_type = str(task.get("type") or task.get("task_type") or "").strip().lower()
    goal = task_goal(task).lower()
    return (
        task_type in {"runtime_mutation_plan", "mutation_plan_graph", "runtime_plan_graph"}
        or "runtime mutation plan graph" in goal
        or "mutation plan graph" in goal
        or "plan graph" in goal
    )



def is_persistent_runtime_session_task(task: Dict[str, Any]) -> bool:
    task_type = str(task.get("type") or task.get("task_type") or "").strip().lower()
    goal = task_goal(task).lower()
    return (
        task_type in {"persistent_runtime_session", "runtime_session", "long_chain_session"}
        or "persistent runtime session" in goal
        or "runtime session" in goal
        or "long-chain session" in goal
    )



def is_runtime_session_resume_task(task: Dict[str, Any]) -> bool:
    task_type = str(task.get("type") or task.get("task_type") or "").strip().lower()
    goal = task_goal(task).lower()
    return (
        task_type in {"runtime_session_resume", "session_resume", "resume_session"}
        or "runtime session resume" in goal
        or "resume runtime session" in goal
        or "session resume" in goal
    )



def is_runtime_session_recovery_finalization_task(task: Dict[str, Any]) -> bool:
    task_type = str(task.get("type") or task.get("task_type") or "").strip().lower()
    goal = task_goal(task).lower()
    return (
        task_type in {"runtime_session_recovery_finalization", "recovery_finalization", "session_recovery_finalization"}
        or "runtime session recovery finalization" in goal
        or "recovery finalization" in goal
        or "finalize runtime session recovery" in goal
    )



def is_runtime_supervisor_task(task: Dict[str, Any]) -> bool:
    task_type = str(task.get("type") or task.get("task_type") or "").strip().lower()
    goal = task_goal(task).lower()
    return (
        task_type in {"runtime_supervisor", "autonomous_runtime_supervisor", "runtime_watchdog"}
        or "runtime supervisor" in goal
        or "autonomous runtime supervisor" in goal
        or "runtime watchdog" in goal
    )


def execute_runtime_supervisor_task(repo_root: Path, task: Dict[str, Any]) -> Dict[str, Any]:
    task_type = str(task.get("type") or "").strip().lower() or "runtime_supervisor"
    goal = task_goal(task)
    current_task_id = task_id(task)

    stale_after_seconds = int(task.get("stale_after_seconds") or 900)
    max_retry_depth = int(task.get("max_retry_depth") or 2)

    artifact = {
        "ok": True,
        "artifact_type": "runtime_supervisor",
        "artifact_path": str(shared_dir(repo_root) / f"{current_task_id}_runtime_supervisor.json"),
        "input_path": "workspace/runtime_sessions",
        "content_preview": "",
        "message": "Prepared runtime supervisor scan.",
    }

    graph_path = update_artifact_graph(
        repo_root=repo_root,
        shared_dir=shared_dir(repo_root),
        task_id=current_task_id,
        goal=goal,
        artifact=artifact,
    )

    result = {
        "ok": True,
        "task_id": current_task_id,
        "type": task_type,
        "goal": goal,
        "runtime_mode": "runtime_supervisor_v1",
        "planner_attached": "runtime_supervisor",
        "executor_attached": "runtime_supervisor",
        "artifact": artifact,
        "artifact_graph_path": str(graph_path),
        "message": f"Runtime supervisor handled task: {goal}",
    }

    result = attach_runtime_ownership_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=current_task_id,
        goal=goal,
        runtime_mode="runtime_supervisor_v1",
    )
    result["runtime_ownership_transition"] = summarize_runtime_ownership_transition(
        result.get("runtime_ownership", {})
    )
    result = attach_execution_authority_handoff_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=current_task_id,
        goal=goal,
    )

    supervisor_record = run_runtime_supervisor(
        repo_root,
        stale_after_seconds=stale_after_seconds,
        max_retry_depth=max_retry_depth,
    )

    result["runtime_supervisor"] = supervisor_record
    result["runtime_supervisor_schema"] = supervisor_record.get("schema")
    result["runtime_supervisor_ok"] = bool(supervisor_record.get("ok"))
    result["runtime_watchdog_scan_ok"] = bool(supervisor_record.get("runtime_watchdog_scan_ok"))
    result["runtime_health_registry_ok"] = bool(supervisor_record.get("runtime_health_registry_ok"))
    result["runtime_incident_queue_ok"] = bool(supervisor_record.get("runtime_incident_queue_ok"))
    result["runtime_recovery_schedule_ok"] = bool(supervisor_record.get("runtime_recovery_schedule_ok"))
    result["runtime_supervisor_journal_path"] = supervisor_record.get("supervisor_journal_path")
    result["ok"] = bool(supervisor_record.get("ok"))

    task["runtime_supervisor"] = supervisor_record
    task["runtime_supervisor_schema"] = supervisor_record.get("schema")
    task["runtime_supervisor_ok"] = bool(supervisor_record.get("ok"))
    task["runtime_supervisor_journal_path"] = supervisor_record.get("supervisor_journal_path")

    current_task_dir = task_dir(repo_root, current_task_id)
    result_path = current_task_dir / "result.json"
    snapshot_path = current_task_dir / "task_snapshot.json"
    runtime_state_path = current_task_dir / "runtime_state.json"

    task["result_path"] = str(result_path)
    task["snapshot_path"] = str(snapshot_path)
    task["runtime_state_path"] = str(runtime_state_path)
    task["artifact_path"] = artifact.get("artifact_path")
    task["artifact_graph_path"] = str(graph_path)

    write_json_file(result_path, result)
    write_json_file(snapshot_path, task)
    write_json_file(
        runtime_state_path,
        {
            "ok": bool(result.get("ok")),
            "task_id": current_task_id,
            "status": "finished" if result.get("ok") else "failed",
            "runtime_mode": "runtime_supervisor_v1",
            "artifact_path": artifact.get("artifact_path"),
            "artifact_graph_path": str(graph_path),
            "result_path": str(result_path),
            "runtime_ownership": result.get("runtime_ownership"),
            "execution_authority_handoff": result.get("execution_authority_handoff"),
            "runtime_supervisor_schema": result.get("runtime_supervisor_schema"),
            "runtime_supervisor_ok": result.get("runtime_supervisor_ok"),
            "runtime_watchdog_scan_ok": result.get("runtime_watchdog_scan_ok"),
            "runtime_health_registry_ok": result.get("runtime_health_registry_ok"),
            "runtime_incident_queue_ok": result.get("runtime_incident_queue_ok"),
            "runtime_recovery_schedule_ok": result.get("runtime_recovery_schedule_ok"),
            "runtime_supervisor_journal_path": result.get("runtime_supervisor_journal_path"),
        },
    )

    return result


def execute_runtime_session_recovery_finalization_task(repo_root: Path, task: Dict[str, Any]) -> Dict[str, Any]:
    task_type = str(task.get("type") or "").strip().lower() or "runtime_session_recovery_finalization"
    goal = task_goal(task)
    current_task_id = task_id(task)
    source_session_id = str(task.get("source_session_id") or "").strip()
    max_resume_depth = int(task.get("max_resume_depth") or 2)

    artifact = {
        "ok": True,
        "artifact_type": "runtime_session_recovery_finalization",
        "artifact_path": str(shared_dir(repo_root) / f"{current_task_id}_runtime_session_recovery_finalization.json"),
        "input_path": source_session_id,
        "content_preview": "",
        "message": "Prepared runtime session recovery finalization.",
    }

    graph_path = update_artifact_graph(
        repo_root=repo_root,
        shared_dir=shared_dir(repo_root),
        task_id=current_task_id,
        goal=goal,
        artifact=artifact,
    )

    result = {
        "ok": True,
        "task_id": current_task_id,
        "type": task_type,
        "goal": goal,
        "runtime_mode": "runtime_session_recovery_finalization_v1",
        "planner_attached": "runtime_session_recovery_finalizer",
        "executor_attached": "runtime_session_recovery_finalization_executor",
        "artifact": artifact,
        "artifact_graph_path": str(graph_path),
        "message": f"Runtime session recovery finalization handled task: {goal}",
    }

    result = attach_runtime_ownership_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=current_task_id,
        goal=goal,
        runtime_mode="runtime_session_recovery_finalization_v1",
    )
    result["runtime_ownership_transition"] = summarize_runtime_ownership_transition(
        result.get("runtime_ownership", {})
    )
    result = attach_execution_authority_handoff_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=current_task_id,
        goal=goal,
    )

    record = finalize_runtime_session_recovery(
        repo_root=repo_root,
        task_id=current_task_id,
        goal=goal,
        source_session_id=source_session_id,
        max_resume_depth=max_resume_depth,
    )

    result["runtime_session_recovery_finalization"] = record
    result["runtime_session_recovery_finalization_schema"] = record.get("schema")
    result["runtime_session_recovery_finalization_status"] = record.get("status")
    result["runtime_session_recovery_finalization_ok"] = bool(record.get("ok"))
    result["runtime_session_recovery_finalization_path"] = record.get("finalization_path")
    result["runtime_session_recovery_escalation_required"] = bool(record.get("escalation_required"))
    result["ok"] = bool(record.get("ok"))

    task["runtime_session_recovery_finalization"] = record
    task["runtime_session_recovery_finalization_schema"] = record.get("schema")
    task["runtime_session_recovery_finalization_status"] = record.get("status")
    task["runtime_session_recovery_finalization_ok"] = bool(record.get("ok"))
    task["runtime_session_recovery_finalization_path"] = record.get("finalization_path")
    task["runtime_session_recovery_escalation_required"] = bool(record.get("escalation_required"))

    current_task_dir = task_dir(repo_root, current_task_id)
    result_path = current_task_dir / "result.json"
    snapshot_path = current_task_dir / "task_snapshot.json"
    runtime_state_path = current_task_dir / "runtime_state.json"

    task["result_path"] = str(result_path)
    task["snapshot_path"] = str(snapshot_path)
    task["runtime_state_path"] = str(runtime_state_path)
    task["artifact_path"] = artifact.get("artifact_path")
    task["artifact_graph_path"] = str(graph_path)

    write_json_file(result_path, result)
    write_json_file(snapshot_path, task)
    write_json_file(
        runtime_state_path,
        {
            "ok": bool(result.get("ok")),
            "task_id": current_task_id,
            "status": "finished" if result.get("ok") else "failed",
            "runtime_mode": "runtime_session_recovery_finalization_v1",
            "artifact_path": artifact.get("artifact_path"),
            "artifact_graph_path": str(graph_path),
            "result_path": str(result_path),
            "runtime_ownership": result.get("runtime_ownership"),
            "execution_authority_handoff": result.get("execution_authority_handoff"),
            "runtime_session_recovery_finalization_schema": result.get("runtime_session_recovery_finalization_schema"),
            "runtime_session_recovery_finalization_status": result.get("runtime_session_recovery_finalization_status"),
            "runtime_session_recovery_finalization_ok": result.get("runtime_session_recovery_finalization_ok"),
            "runtime_session_recovery_finalization_path": result.get("runtime_session_recovery_finalization_path"),
            "runtime_session_recovery_escalation_required": result.get("runtime_session_recovery_escalation_required"),
        },
    )

    return result


def execute_runtime_session_resume_task(repo_root: Path, task: Dict[str, Any]) -> Dict[str, Any]:
    task_type = str(task.get("type") or "").strip().lower() or "runtime_session_resume"
    goal = task_goal(task)
    current_task_id = task_id(task)
    source_session_id = str(task.get("source_session_id") or "").strip()

    artifact = {
        "ok": True,
        "artifact_type": "runtime_session_resume",
        "artifact_path": str(shared_dir(repo_root) / f"{current_task_id}_runtime_session_resume.json"),
        "input_path": source_session_id,
        "content_preview": "",
        "message": "Prepared runtime session resume.",
    }

    graph_path = update_artifact_graph(
        repo_root=repo_root,
        shared_dir=shared_dir(repo_root),
        task_id=current_task_id,
        goal=goal,
        artifact=artifact,
    )

    result = {
        "ok": True,
        "task_id": current_task_id,
        "type": task_type,
        "goal": goal,
        "runtime_mode": "runtime_session_resume_v1",
        "planner_attached": "runtime_session_resume_builder",
        "executor_attached": "runtime_session_resume_executor",
        "artifact": artifact,
        "artifact_graph_path": str(graph_path),
        "message": f"Runtime session resume handled task: {goal}",
    }

    result = attach_runtime_ownership_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=current_task_id,
        goal=goal,
        runtime_mode="runtime_session_resume_v1",
    )
    result["runtime_ownership_transition"] = summarize_runtime_ownership_transition(
        result.get("runtime_ownership", {})
    )
    result = attach_execution_authority_handoff_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=current_task_id,
        goal=goal,
    )
    result = execute_session_resume(
        repo_root=repo_root,
        task=task,
        result=result,
        task_id=current_task_id,
        goal=goal,
        source_session_id=source_session_id,
    )
    result["ok"] = bool(result.get("runtime_session_resume_ok"))

    current_task_dir = task_dir(repo_root, current_task_id)
    result_path = current_task_dir / "result.json"
    snapshot_path = current_task_dir / "task_snapshot.json"
    runtime_state_path = current_task_dir / "runtime_state.json"

    task["result_path"] = str(result_path)
    task["snapshot_path"] = str(snapshot_path)
    task["runtime_state_path"] = str(runtime_state_path)
    task["artifact_path"] = artifact.get("artifact_path")
    task["artifact_graph_path"] = str(graph_path)

    write_json_file(result_path, result)
    write_json_file(snapshot_path, task)
    write_json_file(
        runtime_state_path,
        {
            "ok": bool(result.get("ok")),
            "task_id": current_task_id,
            "status": "finished" if result.get("ok") else "failed",
            "runtime_mode": "runtime_session_resume_v1",
            "artifact_path": artifact.get("artifact_path"),
            "artifact_graph_path": str(graph_path),
            "result_path": str(result_path),
            "runtime_ownership": result.get("runtime_ownership"),
            "execution_authority_handoff": result.get("execution_authority_handoff"),
            "runtime_session_resume_schema": result.get("runtime_session_resume_schema"),
            "runtime_session_resume_status": result.get("runtime_session_resume_status"),
            "runtime_session_resume_ok": result.get("runtime_session_resume_ok"),
            "runtime_session_resume_source_session_id": result.get("runtime_session_resume_source_session_id"),
            "runtime_session_resume_resumed_session_id": result.get("runtime_session_resume_resumed_session_id"),
            "runtime_session_resume_journal_path": result.get("runtime_session_resume_journal_path"),
        },
    )

    return result


def execute_persistent_runtime_session_task(repo_root: Path, task: Dict[str, Any]) -> Dict[str, Any]:
    task_type = str(task.get("type") or "").strip().lower() or "persistent_runtime_session"
    goal = task_goal(task)
    current_task_id = task_id(task)

    target_groups = parse_session_targets(task.get("target_groups") or task.get("targets"), repo_root)
    fail_plan_index = int(task.get("fail_plan_index") or 0)

    artifact = {
        "ok": True,
        "artifact_type": "persistent_runtime_session",
        "artifact_path": str(shared_dir(repo_root) / f"{current_task_id}_persistent_runtime_session.json"),
        "input_path": str(target_groups),
        "content_preview": "",
        "message": "Prepared persistent runtime session.",
    }

    graph_path = update_artifact_graph(
        repo_root=repo_root,
        shared_dir=shared_dir(repo_root),
        task_id=current_task_id,
        goal=goal,
        artifact=artifact,
    )

    result = {
        "ok": True,
        "task_id": current_task_id,
        "type": task_type,
        "goal": goal,
        "runtime_mode": "persistent_runtime_session_v1",
        "planner_attached": "runtime_session_builder",
        "executor_attached": "persistent_runtime_session_executor",
        "artifact": artifact,
        "artifact_graph_path": str(graph_path),
        "message": f"Persistent runtime session handled task: {goal}",
    }

    result = attach_runtime_ownership_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=current_task_id,
        goal=goal,
        runtime_mode="persistent_runtime_session_v1",
    )
    result["runtime_ownership_transition"] = summarize_runtime_ownership_transition(
        result.get("runtime_ownership", {})
    )
    result = attach_execution_authority_handoff_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=current_task_id,
        goal=goal,
    )
    result = execute_persistent_runtime_session(
        repo_root=repo_root,
        task=task,
        result=result,
        task_id=current_task_id,
        goal=goal,
        target_groups=target_groups,
        fail_plan_index=fail_plan_index,
    )
    result["ok"] = bool(result.get("persistent_runtime_session_ok"))

    current_task_dir = task_dir(repo_root, current_task_id)
    result_path = current_task_dir / "result.json"
    snapshot_path = current_task_dir / "task_snapshot.json"
    runtime_state_path = current_task_dir / "runtime_state.json"

    task["result_path"] = str(result_path)
    task["snapshot_path"] = str(snapshot_path)
    task["runtime_state_path"] = str(runtime_state_path)
    task["artifact_path"] = artifact.get("artifact_path")
    task["artifact_graph_path"] = str(graph_path)

    write_json_file(result_path, result)
    write_json_file(snapshot_path, task)
    write_json_file(
        runtime_state_path,
        {
            "ok": bool(result.get("ok")),
            "task_id": current_task_id,
            "status": "finished" if result.get("ok") else "failed",
            "runtime_mode": "persistent_runtime_session_v1",
            "artifact_path": artifact.get("artifact_path"),
            "artifact_graph_path": str(graph_path),
            "result_path": str(result_path),
            "runtime_ownership": result.get("runtime_ownership"),
            "execution_authority_handoff": result.get("execution_authority_handoff"),
            "persistent_runtime_session_schema": result.get("persistent_runtime_session_schema"),
            "persistent_runtime_session_id": result.get("persistent_runtime_session_id"),
            "persistent_runtime_session_status": result.get("persistent_runtime_session_status"),
            "persistent_runtime_session_ok": result.get("persistent_runtime_session_ok"),
            "persistent_runtime_session_journal_path": result.get("persistent_runtime_session_journal_path"),
            "persistent_runtime_session_state_path": result.get("persistent_runtime_session_state_path"),
            "persistent_runtime_session_replay_path": result.get("persistent_runtime_session_replay_path"),
            "persistent_runtime_session_recovery_marker_path": result.get("persistent_runtime_session_recovery_marker_path"),
        },
    )

    return result


def execute_runtime_mutation_plan_task(repo_root: Path, task: Dict[str, Any]) -> Dict[str, Any]:
    task_type = str(task.get("type") or "").strip().lower() or "runtime_mutation_plan"
    goal = task_goal(task)
    current_task_id = task_id(task)

    targets = _normalize_target_list(task.get("targets"))
    if not targets:
        targets = _make_default_batch_targets(repo_root)

    force_failure = bool(task.get("force_verification_failure"))

    artifact = {
        "ok": True,
        "artifact_type": "runtime_mutation_plan_graph",
        "artifact_path": str(shared_dir(repo_root) / f"{current_task_id}_runtime_mutation_plan_graph.json"),
        "input_path": ",".join(targets),
        "content_preview": "",
        "message": "Prepared runtime mutation plan graph.",
    }

    graph_path = update_artifact_graph(
        repo_root=repo_root,
        shared_dir=shared_dir(repo_root),
        task_id=current_task_id,
        goal=goal,
        artifact=artifact,
    )

    result = {
        "ok": True,
        "task_id": current_task_id,
        "type": task_type,
        "goal": goal,
        "runtime_mode": "runtime_mutation_plan_graph_v1",
        "planner_attached": "plan_graph_builder",
        "executor_attached": "runtime_plan_executor",
        "artifact": artifact,
        "artifact_graph_path": str(graph_path),
        "message": f"Runtime mutation plan graph handled task: {goal}",
    }

    result = attach_runtime_ownership_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=current_task_id,
        goal=goal,
        runtime_mode="runtime_mutation_plan_graph_v1",
    )
    result["runtime_ownership_transition"] = summarize_runtime_ownership_transition(
        result.get("runtime_ownership", {})
    )
    result = attach_execution_authority_handoff_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=current_task_id,
        goal=goal,
    )
    result = execute_runtime_mutation_plan_graph(
        repo_root=repo_root,
        task=task,
        result=result,
        task_id=current_task_id,
        goal=goal,
        targets=targets,
        force_verification_failure=force_failure,
    )
    result["ok"] = bool(result.get("runtime_mutation_plan_graph_ok"))

    current_task_dir = task_dir(repo_root, current_task_id)
    result_path = current_task_dir / "result.json"
    snapshot_path = current_task_dir / "task_snapshot.json"
    runtime_state_path = current_task_dir / "runtime_state.json"

    task["result_path"] = str(result_path)
    task["snapshot_path"] = str(snapshot_path)
    task["runtime_state_path"] = str(runtime_state_path)
    task["artifact_path"] = artifact.get("artifact_path")
    task["artifact_graph_path"] = str(graph_path)

    write_json_file(result_path, result)
    write_json_file(snapshot_path, task)
    write_json_file(
        runtime_state_path,
        {
            "ok": bool(result.get("ok")),
            "task_id": current_task_id,
            "status": "finished" if result.get("ok") else "failed",
            "runtime_mode": "runtime_mutation_plan_graph_v1",
            "artifact_path": artifact.get("artifact_path"),
            "artifact_graph_path": str(graph_path),
            "result_path": str(result_path),
            "runtime_ownership": result.get("runtime_ownership"),
            "execution_authority_handoff": result.get("execution_authority_handoff"),
            "runtime_mutation_plan_graph_schema": result.get("runtime_mutation_plan_graph_schema"),
            "runtime_mutation_plan_graph_id": result.get("runtime_mutation_plan_graph_id"),
            "runtime_mutation_plan_graph_status": result.get("runtime_mutation_plan_graph_status"),
            "runtime_mutation_plan_graph_ok": result.get("runtime_mutation_plan_graph_ok"),
            "runtime_mutation_plan_graph_journal_path": result.get("runtime_mutation_plan_graph_journal_path"),
            "runtime_mutation_plan_graph_rollback_applied": result.get("runtime_mutation_plan_graph_rollback_applied"),
        },
    )

    return result


def execute_governed_engineering_batch_task(repo_root: Path, task: Dict[str, Any]) -> Dict[str, Any]:
    task_type = str(task.get("type") or "").strip().lower() or "governed_engineering_batch"
    goal = task_goal(task)
    current_task_id = task_id(task)

    targets = _normalize_target_list(task.get("targets"))
    if not targets:
        targets = _make_default_batch_targets(repo_root)

    force_failure = bool(task.get("force_verification_failure"))

    artifact = {
        "ok": True,
        "artifact_type": "governed_engineering_transaction_batch",
        "artifact_path": str(shared_dir(repo_root) / f"{current_task_id}_governed_engineering_batch.json"),
        "input_path": ",".join(targets),
        "content_preview": "",
        "message": "Prepared governed engineering transaction batch.",
    }

    graph_path = update_artifact_graph(
        repo_root=repo_root,
        shared_dir=shared_dir(repo_root),
        task_id=current_task_id,
        goal=goal,
        artifact=artifact,
    )

    result = {
        "ok": True,
        "task_id": current_task_id,
        "type": task_type,
        "goal": goal,
        "runtime_mode": "governed_engineering_transaction_batch_v1",
        "planner_attached": False,
        "executor_attached": "step_executor_governed_engineering_batch",
        "artifact": artifact,
        "artifact_graph_path": str(graph_path),
        "message": f"Governed engineering transaction batch handled task: {goal}",
    }

    result = attach_runtime_ownership_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=current_task_id,
        goal=goal,
        runtime_mode="governed_engineering_transaction_batch_v1",
    )
    result["runtime_ownership_transition"] = summarize_runtime_ownership_transition(
        result.get("runtime_ownership", {})
    )
    result = attach_execution_authority_handoff_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=current_task_id,
        goal=goal,
    )
    result = attach_governed_engineering_transaction_batch(
        repo_root=repo_root,
        task=task,
        result=result,
        task_id=current_task_id,
        goal=goal,
        targets=targets,
        force_verification_failure=force_failure,
    )
    result["ok"] = bool(result.get("governed_engineering_transaction_batch_ok"))

    current_task_dir = task_dir(repo_root, current_task_id)
    result_path = current_task_dir / "result.json"
    snapshot_path = current_task_dir / "task_snapshot.json"
    runtime_state_path = current_task_dir / "runtime_state.json"

    task["result_path"] = str(result_path)
    task["snapshot_path"] = str(snapshot_path)
    task["runtime_state_path"] = str(runtime_state_path)
    task["artifact_path"] = artifact.get("artifact_path")
    task["artifact_graph_path"] = str(graph_path)

    write_json_file(result_path, result)
    write_json_file(snapshot_path, task)
    write_json_file(
        runtime_state_path,
        {
            "ok": bool(result.get("ok")),
            "task_id": current_task_id,
            "status": "finished" if result.get("ok") else "failed",
            "runtime_mode": "governed_engineering_transaction_batch_v1",
            "artifact_path": artifact.get("artifact_path"),
            "artifact_graph_path": str(graph_path),
            "result_path": str(result_path),
            "runtime_ownership": result.get("runtime_ownership"),
            "execution_authority_handoff": result.get("execution_authority_handoff"),
            "governed_engineering_transaction_batch_schema": result.get("governed_engineering_transaction_batch_schema"),
            "governed_engineering_transaction_batch_id": result.get("governed_engineering_transaction_batch_id"),
            "governed_engineering_transaction_batch_status": result.get("governed_engineering_transaction_batch_status"),
            "governed_engineering_transaction_batch_ok": result.get("governed_engineering_transaction_batch_ok"),
            "governed_engineering_transaction_batch_journal_path": result.get("governed_engineering_transaction_batch_journal_path"),
            "governed_engineering_transaction_batch_rollback_applied": result.get("governed_engineering_transaction_batch_rollback_applied"),
        },
    )

    return result


def execute_controlled_mutation_transaction_task(repo_root: Path, task: Dict[str, Any]) -> Dict[str, Any]:
    task_type = str(task.get("type") or "").strip().lower() or "controlled_mutation_transaction"
    goal = task_goal(task)
    current_task_id = task_id(task)
    target_path = str(task.get("target_path") or task.get("path") or "").strip()
    if not target_path:
        target_path = _extract_mutation_target_from_goal(goal)

    force_failure = bool(task.get("force_verification_failure"))

    artifact = {
        "ok": True,
        "artifact_type": "controlled_mutation_transaction",
        "artifact_path": str(shared_dir(repo_root) / f"{current_task_id}_controlled_mutation_transaction.json"),
        "input_path": target_path,
        "content_preview": "",
        "message": "Prepared controlled mutation transaction.",
    }

    graph_path = update_artifact_graph(
        repo_root=repo_root,
        shared_dir=shared_dir(repo_root),
        task_id=current_task_id,
        goal=goal,
        artifact=artifact,
    )

    result = {
        "ok": True,
        "task_id": current_task_id,
        "type": task_type,
        "goal": goal,
        "runtime_mode": "controlled_mutation_transaction_seal_v1",
        "planner_attached": False,
        "executor_attached": "step_executor_controlled_mutation_transaction",
        "artifact": artifact,
        "artifact_graph_path": str(graph_path),
        "message": f"Controlled mutation transaction handled task: {goal}",
    }

    result = attach_runtime_ownership_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=current_task_id,
        goal=goal,
        runtime_mode="controlled_mutation_transaction_seal_v1",
    )
    result["runtime_ownership_transition"] = summarize_runtime_ownership_transition(
        result.get("runtime_ownership", {})
    )
    result = attach_execution_authority_handoff_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=current_task_id,
        goal=goal,
    )
    result = attach_controlled_mutation_transaction_seal(
        repo_root=repo_root,
        task=task,
        result=result,
        task_id=current_task_id,
        goal=goal,
        target_path=target_path,
        force_verification_failure=force_failure,
    )
    result["ok"] = bool(result.get("controlled_mutation_transaction_ok"))

    current_task_dir = task_dir(repo_root, current_task_id)
    result_path = current_task_dir / "result.json"
    snapshot_path = current_task_dir / "task_snapshot.json"
    runtime_state_path = current_task_dir / "runtime_state.json"

    task["result_path"] = str(result_path)
    task["snapshot_path"] = str(snapshot_path)
    task["runtime_state_path"] = str(runtime_state_path)
    task["artifact_path"] = artifact.get("artifact_path")
    task["artifact_graph_path"] = str(graph_path)

    write_json_file(result_path, result)
    write_json_file(snapshot_path, task)
    write_json_file(
        runtime_state_path,
        {
            "ok": bool(result.get("ok")),
            "task_id": current_task_id,
            "status": "finished" if result.get("ok") else "failed",
            "runtime_mode": "controlled_mutation_transaction_seal_v1",
            "artifact_path": artifact.get("artifact_path"),
            "artifact_graph_path": str(graph_path),
            "result_path": str(result_path),
            "runtime_ownership": result.get("runtime_ownership"),
            "execution_authority_handoff": result.get("execution_authority_handoff"),
            "controlled_mutation_transaction_schema": result.get("controlled_mutation_transaction_schema"),
            "controlled_mutation_transaction_id": result.get("controlled_mutation_transaction_id"),
            "controlled_mutation_transaction_status": result.get("controlled_mutation_transaction_status"),
            "controlled_mutation_transaction_ok": result.get("controlled_mutation_transaction_ok"),
            "controlled_mutation_transaction_journal_path": result.get("controlled_mutation_transaction_journal_path"),
            "controlled_mutation_transaction_rollback_applied": result.get("controlled_mutation_transaction_rollback_applied"),
        },
    )

    return result


def execute_controlled_source_mutation_task(repo_root: Path, task: Dict[str, Any]) -> Dict[str, Any]:
    task_type = str(task.get("type") or "").strip().lower() or "controlled_source_mutation"
    goal = task_goal(task)
    current_task_id = task_id(task)
    target_path = str(task.get("target_path") or task.get("path") or "").strip()
    if not target_path:
        target_path = _extract_mutation_target_from_goal(goal)

    artifact = {
        "ok": True,
        "artifact_type": "controlled_source_mutation",
        "artifact_path": str(shared_dir(repo_root) / f"{current_task_id}_controlled_source_mutation.json"),
        "input_path": target_path,
        "content_preview": "",
        "message": "Prepared controlled source mutation.",
    }

    graph_path = update_artifact_graph(
        repo_root=repo_root,
        shared_dir=shared_dir(repo_root),
        task_id=current_task_id,
        goal=goal,
        artifact=artifact,
    )

    result = {
        "ok": True,
        "task_id": current_task_id,
        "type": task_type,
        "goal": goal,
        "runtime_mode": "controlled_source_mutation_v2",
        "planner_attached": False,
        "executor_attached": "step_executor_controlled_source_mutation",
        "artifact": artifact,
        "artifact_graph_path": str(graph_path),
        "message": f"Controlled source mutation handled task: {goal}",
    }

    result = attach_runtime_ownership_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=current_task_id,
        goal=goal,
        runtime_mode="controlled_source_mutation_v2",
    )
    result["runtime_ownership_transition"] = summarize_runtime_ownership_transition(
        result.get("runtime_ownership", {})
    )
    result = attach_execution_authority_handoff_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=current_task_id,
        goal=goal,
    )
    result = attach_controlled_source_mutation(
        repo_root=repo_root,
        task=task,
        result=result,
        task_id=current_task_id,
        goal=goal,
        target_path=target_path,
    )
    result["ok"] = bool(result.get("controlled_source_mutation_ok"))

    current_task_dir = task_dir(repo_root, current_task_id)
    result_path = current_task_dir / "result.json"
    snapshot_path = current_task_dir / "task_snapshot.json"
    runtime_state_path = current_task_dir / "runtime_state.json"

    task["result_path"] = str(result_path)
    task["snapshot_path"] = str(snapshot_path)
    task["runtime_state_path"] = str(runtime_state_path)
    task["artifact_path"] = artifact.get("artifact_path")
    task["artifact_graph_path"] = str(graph_path)

    write_json_file(result_path, result)
    write_json_file(snapshot_path, task)
    write_json_file(
        runtime_state_path,
        {
            "ok": bool(result.get("ok")),
            "task_id": current_task_id,
            "status": "finished" if result.get("ok") else "failed",
            "runtime_mode": "controlled_source_mutation_v2",
            "artifact_path": artifact.get("artifact_path"),
            "artifact_graph_path": str(graph_path),
            "result_path": str(result_path),
            "runtime_ownership": result.get("runtime_ownership"),
            "execution_authority_handoff": result.get("execution_authority_handoff"),
            "controlled_source_mutation": result.get("controlled_source_mutation"),
            "controlled_source_mutation_schema": result.get("controlled_source_mutation_schema"),
            "controlled_source_mutation_ok": result.get("controlled_source_mutation_ok"),
        },
    )

    return result


def run_ingestion_tasks(repo_root: Path, count: int) -> Optional[Dict[str, Any]]:
    tasks = read_tasks_index(repo_root)
    if not tasks:
        return None

    executed_results: List[Dict[str, Any]] = []
    skipped_blocked: List[Dict[str, Any]] = []
    executed_count = 0
    now = time.time()

    # The dict values point to the same task dictionaries in `tasks`.
    # Updating a producer to finished in this loop immediately unlocks dependents later in the same pass.
    by_id = {task_id(task): task for task in tasks if task_id(task)}

    for task in tasks:
        if executed_count >= count:
            break
        if task_status(task) not in {"created", "queued", "ready", "retry", "retrying"}:
            continue
        if not is_fast_routable_task(task):
            continue

        current_task_id = task_id(task)
        if not deps_satisfied(task, by_id):
            skipped_blocked.append(
                {
                    "task_id": current_task_id,
                    "goal": task_goal(task),
                    "depends_on": task.get("depends_on"),
                    "status": task_status(task),
                }
            )
            continue

        project_runtime_status(task, "running", owner="core/runtime/thin_runtime_bridge.py")
        task["started_at"] = now
        task["runtime_booted"] = False
        task["fast_cli_path"] = True

        if is_runtime_supervisor_task(task):
            result = execute_runtime_supervisor_task(repo_root, task)
        elif is_runtime_session_recovery_finalization_task(task):
            result = execute_runtime_session_recovery_finalization_task(repo_root, task)
        elif is_runtime_session_resume_task(task):
            result = execute_runtime_session_resume_task(repo_root, task)
        elif is_persistent_runtime_session_task(task):
            result = execute_persistent_runtime_session_task(repo_root, task)
        elif is_runtime_mutation_plan_task(task):
            result = execute_runtime_mutation_plan_task(repo_root, task)
        elif is_governed_engineering_batch_task(task):
            result = execute_governed_engineering_batch_task(repo_root, task)
        elif is_controlled_mutation_transaction_task(task):
            result = execute_controlled_mutation_transaction_task(repo_root, task)
        elif is_controlled_source_mutation_task(task):
            result = execute_controlled_source_mutation_task(repo_root, task)
        elif is_controlled_mutation_probe_task(task):
            result = execute_controlled_mutation_task(repo_root, task)
        else:
            result = execute_ingestion_task(repo_root, task)

        project_runtime_status(task, "finished" if result.get("ok") else "failed", owner="core/runtime/thin_runtime_bridge.py")
        task["finished_at"] = time.time()
        task["result"] = result
        executed_results.append(result)
        executed_count += 1

    if executed_count <= 0:
        if skipped_blocked:
            return {
                "ok": True,
                "mode": "thin_execution_bridge_v1",
                "fast_cli_path": True,
                "legacy_app_booted": False,
                "runtime_booted": False,
                "executed_count": 0,
                "executed_results": [],
                "blocked_count": len(skipped_blocked),
                "blocked_tasks": skipped_blocked,
                "message": "No dependency-ready tasks were executable.",
            }
        return None

    write_tasks_index(repo_root, tasks)
    return {
        "ok": True,
        "mode": "thin_execution_bridge_v1",
        "fast_cli_path": True,
        "legacy_app_booted": False,
        "runtime_booted": False,
        "executed_count": executed_count,
        "executed_results": executed_results,
        "blocked_count": len(skipped_blocked),
        "blocked_tasks": skipped_blocked,
    }


def drain_ingestion_tasks(repo_root: Path, max_rounds: int = 50) -> Dict[str, Any]:
    max_rounds = max(1, int(max_rounds or 1))
    rounds: List[Dict[str, Any]] = []
    total_executed = 0
    total_blocked = 0

    for round_index in range(1, max_rounds + 1):
        result = run_ingestion_tasks(repo_root, 1)
        if result is None:
            return {
                "ok": True,
                "mode": "thin_execution_bridge_drain_v1",
                "fast_cli_path": True,
                "legacy_app_booted": False,
                "runtime_booted": False,
                "rounds_used": round_index - 1,
                "max_rounds": max_rounds,
                "executed_count": total_executed,
                "blocked_count": total_blocked,
                "rounds": rounds,
                "drained": True,
                "message": "No executable ready tasks remain.",
            }

        executed_count = int(result.get("executed_count") or 0)
        blocked_count = int(result.get("blocked_count") or 0)
        total_executed += executed_count
        total_blocked += blocked_count
        rounds.append(
            {
                "round": round_index,
                "executed_count": executed_count,
                "blocked_count": blocked_count,
                "executed_results": result.get("executed_results", []),
                "blocked_tasks": result.get("blocked_tasks", []),
            }
        )

        if executed_count <= 0:
            return {
                "ok": True,
                "mode": "thin_execution_bridge_drain_v1",
                "fast_cli_path": True,
                "legacy_app_booted": False,
                "runtime_booted": False,
                "rounds_used": round_index,
                "max_rounds": max_rounds,
                "executed_count": total_executed,
                "blocked_count": total_blocked,
                "rounds": rounds,
                "drained": blocked_count <= 0,
                "message": "Drain stopped because no dependency-ready task was executable.",
            }

    return {
        "ok": True,
        "mode": "thin_execution_bridge_drain_v1",
        "fast_cli_path": True,
        "legacy_app_booted": False,
        "runtime_booted": False,
        "rounds_used": max_rounds,
        "max_rounds": max_rounds,
        "executed_count": total_executed,
        "blocked_count": total_blocked,
        "rounds": rounds,
        "drained": False,
        "message": "Drain stopped at max_rounds.",
    }

