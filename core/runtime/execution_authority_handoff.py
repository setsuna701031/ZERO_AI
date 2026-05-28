from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict


def build_execution_authority_handoff_record(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    artifact: Dict[str, Any],
    result: Dict[str, Any],
    task_id: str,
    goal: str,
) -> Dict[str, Any]:
    """Build the v1 formal authority handoff envelope.

    This is still a safe bridge: it records the transition target and
    authority chain without booting the heavyweight Scheduler graph from the
    fast CLI path.

    Boundary:
    - CLI is not execution owner.
    - Thin bridge is compatibility/fallback.
    - Scheduler owns orchestration.
    - TaskRunner owns runtime authority propagation.
    - StepExecutor remains the governed execution endpoint.
    """

    ownership = result.get("runtime_ownership") if isinstance(result, dict) else {}
    if not isinstance(ownership, dict):
        ownership = {}

    return {
        "schema": "zero.aer.execution_authority_handoff.v1",
        "created_at": time.time(),
        "repo_root": str(repo_root),
        "task_id": task_id,
        "goal": goal,
        "handoff_status": "recorded_not_executed",
        "handoff_mode": "thin_runtime_to_aer_kernel",
        "source_runtime": "core.runtime.thin_runtime_bridge",
        "source_executor": "thin_artifact_writer",
        "target_scheduler": "core.tasks.scheduler.Scheduler",
        "target_task_runner": "core.runtime.task_runner.TaskRunner",
        "target_step_executor": "core.runtime.step_executor.StepExecutor",
        "target_execution_method": "StepExecutor.execute_step",
        "authority_chain": [
            {
                "layer": "cli",
                "module": "cli.task_cli",
                "responsibility": "command dispatch only",
                "execution_owner": False,
            },
            {
                "layer": "scheduler",
                "module": "core.tasks.scheduler.Scheduler",
                "responsibility": "orchestration and queue ownership",
                "execution_owner": False,
            },
            {
                "layer": "task_runner",
                "module": "core.runtime.task_runner.TaskRunner",
                "responsibility": "runtime authority propagation and task execution envelope",
                "execution_owner": False,
            },
            {
                "layer": "step_executor",
                "module": "core.runtime.step_executor.StepExecutor",
                "responsibility": "governed execution endpoint",
                "execution_owner": True,
            },
        ],
        "artifact": {
            "input_path": str(artifact.get("input_path") or ""),
            "artifact_path": str(artifact.get("artifact_path") or ""),
            "artifact_type": str(artifact.get("artifact_type") or ""),
            "output_artifact_is_execution_evidence": False,
        },
        "compatibility": {
            "thin_bridge_fallback_enabled": True,
            "heavy_runtime_booted": False,
            "scheduler_handoff_required_next": True,
            "step_executor_handoff_required_next": True,
        },
        "evidence_boundary": {
            "execution_result_recorded": True,
            "artifact_graph_recorded": bool(result.get("artifact_graph_path")),
            "runtime_ownership_recorded": bool(ownership),
            "authority_handoff_recorded": True,
            "authority_handoff_executed": False,
        },
        "next_stage": {
            "name": "step_executor_artifact_step_bridge_v1",
            "goal": "convert thin artifact writes into StepExecutor-governed step execution",
            "must_not": [
                "move execution authority into CLI",
                "let artifact output impersonate execution evidence",
                "bypass Scheduler or TaskRunner authority propagation in the formal runtime path",
                "introduce hidden mutation shortcuts",
            ],
        },
    }


def attach_execution_authority_handoff_record(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    artifact: Dict[str, Any],
    result: Dict[str, Any],
    task_id: str,
    goal: str,
) -> Dict[str, Any]:
    record = build_execution_authority_handoff_record(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        result=result,
        task_id=task_id,
        goal=goal,
    )

    result["execution_authority_handoff"] = record
    result["execution_authority_handoff_schema"] = record["schema"]
    result["authority_handoff_status"] = record["handoff_status"]

    task["execution_authority_handoff"] = record
    task["execution_authority_handoff_schema"] = record["schema"]
    task["authority_handoff_status"] = record["handoff_status"]

    return result
