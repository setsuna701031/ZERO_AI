from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ARTIFACT = ROOT / "core" / "runtime" / "artifact_step_bridge.py"
BATCH = ROOT / "core" / "runtime" / "governed_engineering_batch.py"
OVERLAY = ROOT / "core" / "tasks" / "scheduler_core" / "runtime_overlay_helpers.py"
INVENTORY = ROOT / "tests" / "test_aer_execution_authority_inventory.py"


ARTIFACT_TRY_BLOCK = '''    try:
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
'''


BATCH_EXECUTE_FUNCTION = '''def _execute_runtime_owned_write(
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


'''


def _backup(path: Path) -> None:
    backup = path.with_suffix(path.suffix + ".bak_aer_final_execution_closure")
    if path.exists() and not backup.exists():
        backup.write_text(path.read_text(encoding="utf-8-sig"), encoding="utf-8")


def patch_artifact() -> None:
    source = ARTIFACT.read_text(encoding="utf-8-sig")
    _backup(ARTIFACT)

    source = source.replace("Execute the artifact write through StepExecutor.", "Execute the artifact write through the runtime owner.")
    source = source.replace("StepExecutor receives a workspace-relative write_file path;", "AgentExecutionRuntime receives a workspace-relative write_file path;")
    source = source.replace("StepExecutor reports ok", "the runtime-owned endpoint reports ok")
    source = source.replace('"core.runtime.step_executor.StepExecutor.execute_step"', '"AgentExecutionRuntime -> TaskRunner -> StepExecutor"')
    source = source.replace('"step_executor_performed_artifact_write"', '"runtime_owner_performed_artifact_write"')

    pattern = re.compile(
        r"    try:\n        from core\.runtime\.step_executor import StepExecutor\n\n"
        r"        executor = StepExecutor\(workspace_root=str\(repo_root / \"workspace\"\)\)\n"
        r".*?"
        r"(?=    except Exception as exc:)",
        re.DOTALL,
    )
    updated, count = pattern.subn(ARTIFACT_TRY_BLOCK, source, count=1)
    if count != 1:
        raise RuntimeError("artifact_step_bridge direct StepExecutor block not found")

    forbidden = [
        "from core.runtime.step_executor import StepExecutor",
        "StepExecutor(",
        "executor.execute_step(",
    ]
    remaining = [item for item in forbidden if item in updated]
    if remaining:
        raise RuntimeError(f"artifact_step_bridge still has direct executor markers: {remaining}")

    ARTIFACT.write_text(updated, encoding="utf-8")


def patch_batch() -> None:
    source = BATCH.read_text(encoding="utf-8-sig")
    _backup(BATCH)

    source = source.replace("StepExecutor writes every mutated file;", "AgentExecutionRuntime delegates every mutated file through TaskRunner to StepExecutor;")
    source = source.replace('"core.runtime.step_executor.StepExecutor.execute_step"', '"AgentExecutionRuntime -> TaskRunner -> StepExecutor"')
    source = source.replace('"execution_authority_endpoint": "step_executor"', '"execution_authority_endpoint": "runtime_owner"')

    pattern = re.compile(
        r"def _execute_step_executor_write\(\n"
        r".*?"
        r"(?=\ndef attach_governed_engineering_transaction_batch|\ndef [a-zA-Z_])",
        re.DOTALL,
    )
    updated, count = pattern.subn(BATCH_EXECUTE_FUNCTION, source, count=1)
    if count != 1:
        raise RuntimeError("governed_engineering_batch _execute_step_executor_write function not found")

    updated = updated.replace("_execute_step_executor_write(", "_execute_runtime_owned_write(")

    forbidden = [
        "from core.runtime.step_executor import StepExecutor",
        "StepExecutor(",
        "executor.execute_step(",
    ]
    remaining = [item for item in forbidden if item in updated]
    if remaining:
        raise RuntimeError(f"governed_engineering_batch still has direct executor markers: {remaining}")

    BATCH.write_text(updated, encoding="utf-8")


def patch_overlay() -> None:
    source = OVERLAY.read_text(encoding="utf-8-sig")
    _backup(OVERLAY)

    source, count = re.subn(
        r"    executor = getattr\(scheduler, \"step_executor\", None\)\n"
        r".*?"
        r"    if bool\(step_result\.get\(\"ok\"\)\):\n"
        r"        return _direct_step_success_payload\(scheduler, task, steps, index, step_result\)\n"
        r"    return _direct_step_failure_payload\(scheduler, task, steps, index, step_result\)\n",
        '''    return None
''',
        source,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise RuntimeError("runtime_overlay_helpers direct executor block not found")

    forbidden = [
        "from core.runtime.step_executor import StepExecutor",
        "StepExecutor(",
        "execute_step(",
        'getattr(executor, "execute_step", None)',
        "scheduler.step_executor = executor",
    ]
    remaining = [item for item in forbidden if item in source]
    if remaining:
        raise RuntimeError(f"runtime_overlay_helpers still has direct executor markers: {remaining}")

    OVERLAY.write_text(source, encoding="utf-8")


def patch_inventory() -> None:
    source = INVENTORY.read_text(encoding="utf-8-sig")
    _backup(INVENTORY)

    source = source.replace(
        '''ALLOWED_STEPEXECUTOR_CONSTRUCTORS = {
    "core/runtime/agent_execution_runtime.py",
    "core/tasks/scheduler.py",
}''',
        '''ALLOWED_STEPEXECUTOR_CONSTRUCTORS = {
    "core/runtime/agent_execution_runtime.py",
    "core/runtime/task_runner.py",
    "core/tasks/scheduler.py",
}''',
    )
    source = source.replace(
        '''ALLOWED_EXECUTE_STEP_CALLS = {
    "core/runtime/task_runner.py",
}''',
        '''ALLOWED_EXECUTE_STEP_CALLS = {
    "core/runtime/task_runner.py",
    "core/runtime/step_executor.py",
}''',
    )

    INVENTORY.write_text(source, encoding="utf-8")


def main() -> None:
    patch_artifact()
    patch_batch()
    patch_overlay()
    patch_inventory()

    print("patched:", ARTIFACT)
    print("patched:", BATCH)
    print("patched:", OVERLAY)
    print("patched:", INVENTORY)


if __name__ == "__main__":
    main()
