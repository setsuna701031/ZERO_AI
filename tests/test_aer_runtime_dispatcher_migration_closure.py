from __future__ import annotations

from pathlib import Path

from core.agent.agent_loop import AgentLoop
from core.runtime.aer_runtime_integration import AERRuntimeIntegration
from core.runtime.runtime_dispatcher import RuntimeDispatcher
from core.runtime.step_executor import StepExecutor
from core.runtime.task_runner import TaskRunner
from tests.test_agent_loop_code_chain_controlled_self_edit_bridge import CodeFixPlanner


def test_agent_loop_code_chain_without_dispatcher_lineage_is_blocked(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "shared" / "blocked.py"
    target.parent.mkdir(parents=True)
    target.write_text("def status():\n    return 'broken'\n", encoding="utf-8")
    result = AgentLoop(
        planner=CodeFixPlanner("workspace/shared/blocked.py", tmp_path),
        step_executor=StepExecutor(workspace_root=workspace),
        repo_root=str(tmp_path),
    ).run("fix a code failure in a sandbox/workcopy file")
    assert result["ok"] is False
    assert result["status"] == "migration_required"
    assert result["execution"]["executed"] is False
    assert target.read_text(encoding="utf-8").endswith("return 'broken'\n")


def test_aer_execute_step_without_dispatcher_lineage_is_blocked(tmp_path: Path) -> None:
    integration = AERRuntimeIntegration(storage_path=tmp_path / "aer.json")
    task = integration.accept_task(goal="blocked", source_session_id="session-a")
    result = integration._execute_step(
        task=task,
        step={"id": "step-a", "type": "respond"},
        step_index=1,
        step_runner=lambda *_args, **_kwargs: {"ok": True},
    )
    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["error"] == "legacy_runtime_dispatcher_migration_required"


def test_direct_bare_step_executor_production_path_is_rejected(tmp_path: Path) -> None:
    result = StepExecutor(workspace_root=tmp_path).execute_step(
        {"id": "step-a", "type": "command", "command": "echo denied"},
        task={"task_id": "task-a"},
        context={},
    )
    assert result["ok"] is False
    assert result["executed"] is False


def test_direct_bare_taskrunner_production_path_is_rejected(tmp_path: Path) -> None:
    result = TaskRunner(step_executor=StepExecutor(workspace_root=tmp_path)).execute_owned_step(
        {"id": "step-a", "type": "command", "command": "echo denied"},
        task={"task_id": "task-a"},
    )
    assert result["ok"] is False
    assert result["executed"] is False
    assert result["blocked"] is True


def test_valid_runtime_dispatcher_lineage_still_executes(tmp_path: Path) -> None:
    task = {
        "task_id": "task-a",
        "package_id": "package-a",
        "session_id": "session-a",
    }
    task["runtime_execution_capability"] = RuntimeDispatcher._execution_capability(task)
    result = TaskRunner(step_executor=StepExecutor(workspace_root=tmp_path)).execute_owned_step(
        {"id": "step-a", "type": "command", "command": "echo allowed"},
        task=task,
    )
    assert result["ok"] is True
    assert result["executed"] is True
