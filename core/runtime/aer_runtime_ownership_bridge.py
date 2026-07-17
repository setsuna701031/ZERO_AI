from __future__ import annotations

import inspect
import time
from pathlib import Path
from typing import Any, Dict


def _class_available(module_name: str, class_name: str) -> Dict[str, Any]:
    try:
        module = __import__(module_name, fromlist=[class_name])
        cls = getattr(module, class_name, None)
        if cls is None:
            return {"available": False, "module": module_name, "class": class_name, "reason": "class_not_found"}
        return {"available": True, "module": module_name, "class": class_name, "callable": callable(cls)}
    except Exception as exc:
        return {
            "available": False,
            "module": module_name,
            "class": class_name,
            "reason": exc.__class__.__name__,
            "message": str(exc),
        }


def _method_available(module_name: str, class_name: str, method_name: str) -> Dict[str, Any]:
    status = _class_available(module_name, class_name)
    if not status.get("available"):
        status["method"] = method_name
        status["method_available"] = False
        return status

    try:
        module = __import__(module_name, fromlist=[class_name])
        cls = getattr(module, class_name)
        method = getattr(cls, method_name, None)
        status["method"] = method_name
        status["method_available"] = callable(method)
        if callable(method):
            try:
                status["signature"] = str(inspect.signature(method))
            except Exception:
                status["signature"] = ""
        return status
    except Exception as exc:
        status["method"] = method_name
        status["method_available"] = False
        status["reason"] = exc.__class__.__name__
        status["message"] = str(exc)
        return status


def build_runtime_kernel_surface_probe() -> Dict[str, Any]:
    return {
        "scheduler": {
            "class": _class_available("core.tasks.scheduler", "Scheduler"),
            "tick": _method_available("core.tasks.scheduler", "Scheduler", "tick"),
            "run_one_step": _method_available("core.tasks.scheduler", "Scheduler", "run_one_step"),
        },
        "task_runner": {
            "class": _class_available("core.runtime.task_runner", "TaskRunner"),
            "run_one_step": _method_available("core.runtime.task_runner", "TaskRunner", "_run_one_step"),
        },
        "step_executor": {
            "class": _class_available("core.runtime.step_executor", "StepExecutor"),
            "execute_step": _method_available("core.runtime.step_executor", "StepExecutor", "execute_step"),
        },
    }


def build_runtime_ownership_record(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    artifact: Dict[str, Any],
    task_id: str,
    goal: str,
    runtime_mode: str = "thin_execution_bridge_v1",
) -> Dict[str, Any]:
    artifact_path = str(artifact.get("artifact_path") or "")
    input_path = str(artifact.get("input_path") or "")
    artifact_type = str(artifact.get("artifact_type") or "")

    return {
        "schema": "zero.aer.runtime_ownership_bridge.v1",
        "created_at": time.time(),
        "repo_root": str(repo_root),
        "task_id": task_id,
        "goal": goal,
        "runtime_mode": runtime_mode,
        "current_owner": "core.runtime.thin_runtime_bridge",
        "current_executor": "thin_artifact_writer",
        "formal_owner_chain": [
            "core.tasks.scheduler.Scheduler",
            "core.runtime.task_runner.TaskRunner",
            "core.runtime.step_executor.StepExecutor",
        ],
        "formal_execution_endpoint": "core.runtime.step_executor.StepExecutor.execute_step",
        "ownership_status": "thin_bridge_recorded",
        "kernel_handoff_ready": True,
        "kernel_handoff_executed": False,
        "execution_authority_endpoint": "thin_artifact_writer",
        "target_execution_authority_endpoint": "step_executor",
        "scheduler_required": True,
        "taskrunner_required": True,
        "step_executor_required": True,
        "artifact": {
            "artifact_path": artifact_path,
            "input_path": input_path,
            "artifact_type": artifact_type,
            "output_artifact_is_execution_evidence": False,
        },
        "boundaries": {
            "cli_is_not_execution_owner": True,
            "thin_bridge_is_temporary_execution_bridge": True,
            "scheduler_remains_orchestration": True,
            "taskrunner_remains_authority_propagation": True,
            "step_executor_remains_governed_execution_endpoint": True,
            "artifact_output_is_not_evidence": True,
            "no_hidden_mutation_shortcut": True,
        },
        "surface_probe": build_runtime_kernel_surface_probe(),
    }


def attach_runtime_ownership_record(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    artifact: Dict[str, Any],
    result: Dict[str, Any],
    task_id: str,
    goal: str,
    runtime_mode: str = "thin_execution_bridge_v1",
) -> Dict[str, Any]:
    record = build_runtime_ownership_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        task_id=task_id,
        goal=goal,
        runtime_mode=runtime_mode,
    )

    result["runtime_ownership"] = record
    result["runtime_ownership_schema"] = record["schema"]
    result["formal_execution_endpoint"] = record["formal_execution_endpoint"]

    task["runtime_ownership"] = record
    task["runtime_ownership_schema"] = record["schema"]
    task["formal_execution_endpoint"] = record["formal_execution_endpoint"]

    return result


def summarize_runtime_ownership_transition(record: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(record, dict):
        return {
            "ok": False,
            "schema": "zero.aer.runtime_ownership_transition_summary.v1",
            "reason": "missing_runtime_ownership_record",
        }

    boundaries = record.get("boundaries") if isinstance(record.get("boundaries"), dict) else {}
    surface_probe = record.get("surface_probe") if isinstance(record.get("surface_probe"), dict) else {}

    scheduler = surface_probe.get("scheduler") if isinstance(surface_probe.get("scheduler"), dict) else {}
    task_runner = surface_probe.get("task_runner") if isinstance(surface_probe.get("task_runner"), dict) else {}
    step_executor = surface_probe.get("step_executor") if isinstance(surface_probe.get("step_executor"), dict) else {}

    scheduler_ok = bool((scheduler.get("class") or {}).get("available"))
    task_runner_ok = bool((task_runner.get("class") or {}).get("available"))
    step_executor_ok = bool((step_executor.get("class") or {}).get("available"))

    boundary_ok = all(
        bool(boundaries.get(key))
        for key in (
            "cli_is_not_execution_owner",
            "scheduler_remains_orchestration",
            "taskrunner_remains_authority_propagation",
            "step_executor_remains_governed_execution_endpoint",
            "artifact_output_is_not_evidence",
            "no_hidden_mutation_shortcut",
        )
    )

    return {
        "ok": scheduler_ok and task_runner_ok and step_executor_ok and boundary_ok,
        "schema": "zero.aer.runtime_ownership_transition_summary.v1",
        "scheduler_surface_available": scheduler_ok,
        "taskrunner_surface_available": task_runner_ok,
        "step_executor_surface_available": step_executor_ok,
        "boundary_ok": boundary_ok,
        "formal_execution_endpoint": record.get("formal_execution_endpoint"),
        "kernel_handoff_ready": bool(record.get("kernel_handoff_ready")),
        "kernel_handoff_executed": bool(record.get("kernel_handoff_executed")),
    }
