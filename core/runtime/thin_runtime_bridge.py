from __future__ import annotations

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
        )
    )
    return task_type in {"ask", "chat", "summarize", "report", "markdown_report"} or routable_goal


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
        return build_markdown_report_artifact(repo_root, current_shared_dir, goal)

    if task_type == "summarize" or "summarize" in lowered or "summary" in lowered or "摘要" in goal:
        return build_summary_artifact(repo_root, current_shared_dir, goal)

    if "hello world" in lowered and ("python" in lowered or "py" in lowered):
        return build_python_hello_world_artifact(repo_root, current_shared_dir, current_task_id)

    if "分析" in goal or "system" in lowered or "目前系統" in goal:
        tasks = read_tasks_index(repo_root)
        queued = sum(1 for item in tasks if task_status(item) == "queued")
        finished = sum(1 for item in tasks if task_status(item) == "finished")
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
        if task_status(task) not in {"queued", "ready", "retry", "retrying"}:
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

        task["status"] = "running"
        task["started_at"] = now
        task["runtime_booted"] = False
        task["fast_cli_path"] = True

        if is_runtime_mutation_plan_task(task):
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

        task["status"] = "finished" if result.get("ok") else "failed"
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

