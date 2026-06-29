from __future__ import annotations

from pathlib import Path
from typing import Any
import pytest

pytestmark = [pytest.mark.contract]




def test_scheduler_write_file_surface_delegates_to_step_executor(
    tmp_path: Path,
) -> None:
    recorder = _RecordingStepExecutor()
    scheduler = _make_scheduler(tmp_path, step_executor=recorder)
    target = tmp_path / "shared" / "scheduler-no-direct-write.txt"

    result = scheduler._execute_simple_step(
        task={
            "task_id": "task-no-direct-write",
            "task_dir": str(tmp_path / "tasks" / "task-no-direct-write"),
            "execution_authority": _execution_authority("mutation"),
            "authority_propagation_required": True,
        },
        step={
            "type": "write_file",
            "path": "workspace/shared/scheduler-no-direct-write.txt",
            "content": "scheduler must not write this",
        },
    )

    assert result["source"] == "step_executor"
    assert recorder.calls[0]["step"]["type"] == "write_file"
    assert recorder.calls[0]["context"]["authority_context"]["authority_role"] == "canonical_delegation"
    assert recorder.calls[0]["context"]["authority_context"]["authority_layer"] == "task_runner"
    assert not target.exists()


def test_scheduler_apply_patch_surface_delegates_to_step_executor(
    tmp_path: Path,
) -> None:
    recorder = _RecordingStepExecutor()
    scheduler = _make_scheduler(tmp_path, step_executor=recorder)

    result = scheduler._execute_simple_step(
        task={
            "task_id": "task-no-direct-patch",
            "task_dir": str(tmp_path / "tasks" / "task-no-direct-patch"),
            "execution_authority": _execution_authority("mutation"),
            "authority_propagation_required": True,
        },
        step={
            "type": "apply_patch",
            "target_path": "workspace/shared/no-direct-patch.txt",
            "old_text": "before",
            "new_text": "after",
        },
    )

    assert result["source"] == "step_executor"
    assert recorder.calls[0]["step"]["type"] == "apply_patch"
    assert recorder.calls[0]["context"]["authority_context"][
        "execution_authority_granted"
    ] is False


def test_scheduler_code_edit_delegates_patch_without_direct_write(
    tmp_path: Path,
) -> None:
    recorder = _RecordingStepExecutor()
    scheduler = _make_scheduler(tmp_path, step_executor=recorder)
    source = tmp_path / "shared" / "math_code.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "def add(a, b):\n"
        "    return a - b\n",
        encoding="utf-8",
    )

    result = scheduler._execute_code_edit_step(
        task={
            "task_id": "task-code-edit-delegates",
            "task_dir": str(tmp_path / "tasks" / "task-code-edit-delegates"),
            "execution_authority": _execution_authority("mutation"),
            "authority_propagation_required": True,
        },
        step={
            "type": "code_edit",
            "path": "shared/math_code.py",
            "target": "function:add",
            "instruction": "fix add",
            "edit_mode": "direct_workspace_edit",
        },
    )

    assert result["action"] == "code_edit_delegated"
    assert result["delegated_to"] == "step_executor"
    assert result["scheduler_direct_mutation"] is False
    assert recorder.calls[0]["step"]["type"] == "apply_patch"
    assert "new_text" in recorder.calls[0]["step"]
    assert source.read_text(encoding="utf-8") == "def add(a, b):\n    return a - b\n"


def test_scheduler_multi_code_edit_delegates_patch_without_direct_write(
    tmp_path: Path,
) -> None:
    recorder = _RecordingStepExecutor()
    scheduler = _make_scheduler(tmp_path, step_executor=recorder)
    source = tmp_path / "shared" / "multi_math.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "def add(a, b):\n"
        "    return a - b\n",
        encoding="utf-8",
    )

    result = scheduler._execute_code_edit_step(
        task={
            "task_id": "task-multi-code-edit-delegates",
            "task_dir": str(tmp_path / "tasks" / "task-multi-code-edit-delegates"),
            "execution_authority": _execution_authority("mutation"),
            "authority_propagation_required": True,
        },
        step={
            "type": "multi_code_edit",
            "edits": [
                {
                    "path": "shared/multi_math.py",
                    "target": "function:add",
                    "instruction": "fix add",
                    "edit_mode": "direct_workspace_edit",
                }
            ],
        },
    )

    assert result["action"] == "multi_code_edit_delegated"
    assert result["delegated_to"] == "step_executor"
    assert result["scheduler_direct_mutation"] is False
    assert recorder.calls[0]["step"]["type"] == "apply_patch"
    assert recorder.calls[0]["step"]["patches"][0]["target_path"] == (
        "shared/multi_math.py"
    )
    assert source.read_text(encoding="utf-8") == "def add(a, b):\n    return a - b\n"


def test_scheduler_code_chain_repair_bridge_delegates_with_orchestration_context(
    tmp_path: Path,
) -> None:
    recorder = _RecordingStepExecutor()
    scheduler = _make_scheduler(tmp_path, step_executor=recorder)

    result = scheduler._execute_simple_step(
        task={
            "task_id": "task-code-chain-delegates",
            "steps": [{"type": "code_chain_repair"}],
            "execution_authority": _execution_authority("mutation"),
            "authority_propagation_required": True,
        },
        step={
            "type": "code_chain_repair",
            "target_path": "workspace/shared/code_chain.py",
        },
    )

    assert result["source"] == "step_executor"
    assert recorder.calls[0]["step"]["type"] == "code_chain_repair"
    assert recorder.calls[0]["context"]["authority_context"]["authority_layer"] == "task_runner"
    assert recorder.calls[0]["context"]["authority_context"][
        "execution_authority_granted"
    ] is False


def test_mutation_still_requires_step_executor_authority_validation(
    tmp_path: Path,
) -> None:
    from core.runtime.step_executor import StepExecutor

    executor = StepExecutor(workspace_root=str(tmp_path))
    result = executor.execute_step(
        step={
            "type": "write_file",
            "path": "workspace/shared/blocked.txt",
            "content": "blocked",
        },
        context={
            "authority_propagation_required": True,
            "authority_context": {
                "authority_layer": "scheduler",
                "execution_authority_granted": False,
            },
        },
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["executed"] is False
    assert result["authority_decision"]["decision"] == "denied"
    assert not (tmp_path / "shared" / "blocked.txt").exists()


def test_taskrunner_authority_context_remains_pass_through(tmp_path: Path) -> None:
    from core.runtime.runtime_dispatcher import RuntimeDispatcher
    from core.runtime.task_runner import TaskRunner

    runner = TaskRunner(step_executor=_RecordingStepExecutor(), debug=False)
    scheduler_context = _make_scheduler(tmp_path)._build_scheduler_authority_context(
        {
            "task_id": "task-runner-pass-through",
            "authority_propagation_required": True,
            "execution_authority": _execution_authority("mutation"),
        }
    )
    context = runner._build_taskrunner_authority_context(
        task={
            "task_id": "task-runner-pass-through",
            "authority_context": scheduler_context,
            "runtime_execution_capability": RuntimeDispatcher._execution_capability(
                {
                    "task_id": "task-runner-pass-through",
                    "package_id": "",
                    "session_id": "",
                }
            ),
        },
        state={},
        step={"type": "apply_patch"},
        upstream_context={},
    )

    assert context["authority_role"] == "canonical_delegation"
    assert context["execution_authority_granted"] is False
    assert context["can_execute_privileged_step"] is True
    assert context["execution_authority"]["descriptive_only"] is True


def _make_scheduler(tmp_path: Path, step_executor: Any | None = None) -> Any:
    from core.tasks.scheduler import Scheduler

    return Scheduler(
        workspace_dir=str(tmp_path),
        step_executor=step_executor,
        allow_commands=True,
        debug=False,
    )


def _execution_authority(action_type: str) -> dict[str, Any]:
    return {
        "authority_source": "human_review",
        "authority_status": "allowed",
        "execution_authority_endpoint": "step_executor",
        "action_type": action_type,
        "ownership_source": "human_review",
        "authority_scope": "scheduler_no_direct_mutation",
    }


class _RecordingStepExecutor:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def execute_step(
        self,
        *,
        step: dict[str, Any],
        task: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "step": step,
                "task": task,
                "context": context,
                "kwargs": kwargs,
            }
        )
        return {
            "ok": True,
            "source": "step_executor",
            "step_type": str(step.get("type") or ""),
            "authority_decision": {
                "authority_phase": "pre_execution",
                "authority_required": True,
                "action_type": "mutation",
                "step_type": str(step.get("type") or ""),
                "decision": "allowed",
                "authority_source": "human_review",
                "sealed": False,
                "reason": "explicit_step_executor_authority",
            },
        }
