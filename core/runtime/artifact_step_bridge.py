from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict


def _step_path_for_executor(repo_root: Path, artifact_path: str) -> str:
    """Return the safest path shape for StepExecutor write_file.

    StepExecutor is constructed with workspace_root=<repo>/workspace.
    Existing deterministic planner examples use paths like shared/hello.py.
    Therefore artifact paths under <repo>/workspace should be passed as
    workspace-relative paths such as shared/report.md, not absolute paths.
    """

    raw = str(artifact_path or "").strip()
    if not raw:
        return ""

    try:
        path = Path(raw)
        workspace_root = (repo_root / "workspace").resolve()
        resolved = path.resolve() if path.is_absolute() else (repo_root / path).resolve()

        try:
            rel = resolved.relative_to(workspace_root)
            return rel.as_posix()
        except Exception:
            pass

        try:
            rel_repo = resolved.relative_to(repo_root.resolve())
            return rel_repo.as_posix()
        except Exception:
            pass

        return raw.replace("\\", "/")
    except Exception:
        return raw.replace("\\", "/")


def _build_write_file_step(repo_root: Path, artifact: Dict[str, Any]) -> Dict[str, Any]:
    artifact_path = str(artifact.get("artifact_path") or "").strip()
    content = str(artifact.get("content_preview") or "")
    return {
        "type": "write_file",
        "path": _step_path_for_executor(repo_root, artifact_path),
        "content": content,
        "scope": "shared",
        "source": "artifact_step_bridge",
        "artifact_type": str(artifact.get("artifact_type") or ""),
    }


def _step_result_ok(step_result: Any, artifact_path: str) -> bool:
    if isinstance(step_result, dict) and bool(step_result.get("ok", False)):
        return True
    try:
        return bool(artifact_path and Path(str(artifact_path)).exists())
    except Exception:
        return False


def execute_artifact_step_via_step_executor(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    artifact: Dict[str, Any],
    task_id: str,
    goal: str,
) -> Dict[str, Any]:
    """Execute the artifact write through the runtime owner.

    v1.1 fixes the path handoff:
    - thin artifact payload is still prepared before this bridge;
    - AgentExecutionRuntime receives a workspace-relative write_file path;
    - the record is only marked ok when the runtime-owned endpoint reports ok or the governed
      file write surface leaves the expected artifact in place.
    """

    artifact_path = str(artifact.get("artifact_path") or "").strip()
    step = _build_write_file_step(repo_root, artifact)
    if not step.get("path"):
        return {
            "ok": False,
            "schema": "zero.aer.step_executor_artifact_step_bridge.v1_1",
            "created_at": time.time(),
            "task_id": task_id,
            "goal": goal,
            "handoff_executed": False,
            "error": "artifact_path_missing",
            "step": step,
        }

    try:
        from core.runtime.agent_execution_runtime import AgentExecutionRuntime

        runtime = AgentExecutionRuntime(workspace_root=str(repo_root / "workspace"))
        step_task = {
            "task_id": task_id,
            "task_name": task_id,
            "goal": goal,
            "runtime_mode": "thin_execution_bridge_v1",
            "workspace_root": str(repo_root / "workspace"),
            "shared_dir": str(repo_root / "workspace" / "shared"),
            "task_dir": str(repo_root / "workspace" / "tasks" / task_id),
            "execution_authority_handoff": task.get("execution_authority_handoff"),
            "execution_authority": task.get("execution_authority"),
            "authority_context": task.get("authority_context"),
            "runtime_authority_context": task.get("runtime_authority_context"),
            "runtime_ownership": task.get("runtime_ownership"),
        }
        step_context = {
            "repo_root": str(repo_root),
            "workspace_root": str(repo_root / "workspace"),
            "shared_dir": str(repo_root / "workspace" / "shared"),
            "task_dir": str(repo_root / "workspace" / "tasks" / task_id),
            "artifact_step_bridge": True,
            "formal_execution_endpoint": "AgentExecutionRuntime -> TaskRunner -> StepExecutor",
            "direct_execution": False,
            "runtime_owns_execution": True,
            "taskrunner_required": True,
            "step_executor_endpoint_only": True,
        }
        step_result = runtime.run_step(
            step=step,
            task=step_task,
            context=step_context,
        )
        ok = _step_result_ok(step_result, artifact_path)
        return {
            "ok": ok,
            "schema": "zero.aer.runtime_owned_artifact_step_bridge.v1",
            "created_at": time.time(),
            "task_id": task_id,
            "goal": goal,
            "handoff_executed": True,
            "formal_execution_endpoint": "AgentExecutionRuntime -> TaskRunner -> StepExecutor",
            "step": step,
            "step_result": step_result,
            "execution_authority_endpoint": "runtime_owner",
            "thin_writer_payload_reused": True,
            "artifact_path": artifact_path,
            "artifact_type": artifact.get("artifact_type"),
            "direct_execution": False,
            "runtime_owns_execution": True,
            "taskrunner_required": True,
            "step_executor_endpoint_only": True,
            "authority_path": "ArtifactStepBridge -> AgentExecutionRuntime -> TaskRunner -> StepExecutor",
            "boundary": {
                "cli_is_not_execution_owner": True,
                "thin_bridge_is_compatibility_layer": True,
                "runtime_owner_performed_artifact_write": ok,
                "artifact_output_is_not_execution_evidence": True,
                "no_hidden_mutation_shortcut": True,
            },
        }
    except Exception as exc:
        return {
            "ok": False,
            "schema": "zero.aer.step_executor_artifact_step_bridge.v1_1",
            "created_at": time.time(),
            "task_id": task_id,
            "goal": goal,
            "handoff_executed": False,
            "formal_execution_endpoint": "AgentExecutionRuntime -> TaskRunner -> StepExecutor",
            "step": step,
            "error": {
                "type": exc.__class__.__name__,
                "message": str(exc),
            },
            "execution_authority_endpoint": "thin_artifact_writer_fallback",
            "thin_writer_payload_reused": True,
            "artifact_path": artifact_path,
            "artifact_type": artifact.get("artifact_type"),
        }


def attach_step_executor_artifact_execution(
    *,
    repo_root: Path,
    task: Dict[str, Any],
    artifact: Dict[str, Any],
    result: Dict[str, Any],
    task_id: str,
    goal: str,
) -> Dict[str, Any]:
    record = execute_artifact_step_via_step_executor(
        repo_root=repo_root,
        task=task,
        artifact=artifact,
        task_id=task_id,
        goal=goal,
    )

    result["step_executor_artifact_execution"] = record
    result["step_executor_artifact_execution_schema"] = record.get("schema")
    result["step_executor_handoff_executed"] = bool(record.get("handoff_executed"))
    result["step_executor_artifact_execution_ok"] = bool(record.get("ok"))

    task["step_executor_artifact_execution"] = record
    task["step_executor_artifact_execution_schema"] = record.get("schema")
    task["step_executor_handoff_executed"] = bool(record.get("handoff_executed"))
    task["step_executor_artifact_execution_ok"] = bool(record.get("ok"))

    handoff = result.get("execution_authority_handoff")
    if isinstance(handoff, dict):
        if bool(record.get("ok")):
            handoff["handoff_status"] = "step_executor_artifact_bridge_executed"
            handoff["authority_handoff_status"] = "step_executor_artifact_bridge_executed"
        else:
            handoff["handoff_status"] = "step_executor_artifact_bridge_attempted"
            handoff["authority_handoff_status"] = "step_executor_artifact_bridge_attempted"

        evidence_boundary = handoff.get("evidence_boundary")
        if isinstance(evidence_boundary, dict):
            evidence_boundary["authority_handoff_executed"] = bool(record.get("handoff_executed"))
            evidence_boundary["step_executor_artifact_execution_recorded"] = True
            evidence_boundary["step_executor_artifact_execution_ok"] = bool(record.get("ok"))

        compatibility = handoff.get("compatibility")
        if isinstance(compatibility, dict):
            compatibility["step_executor_handoff_required_next"] = not bool(record.get("ok"))
            compatibility["step_executor_artifact_bridge_executed"] = bool(record.get("handoff_executed"))

        result["authority_handoff_status"] = handoff["handoff_status"]
        task["execution_authority_handoff"] = handoff
        task["authority_handoff_status"] = handoff["handoff_status"]

    return result
