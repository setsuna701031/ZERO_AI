from __future__ import annotations

from pathlib import Path

import pytest

from core.planning.work_package_planner_bridge import WorkPackagePlannerBridge
from core.runtime.runtime_dispatcher import RuntimeDispatcher
from core.runtime.step_executor import StepExecutor
from core.runtime.task_runner import TaskRunner
from core.runtime.work_package_operator import RuntimeWorkPackageOperator
from core.runtime.work_package_queue import RuntimePackageQueue


def _authority(source: str = "runtime_dispatcher") -> dict:
    return {
        "task_id": "runtime-task",
        "step_id": "runtime-step",
        "authority_source": source,
        "authority_status": "allowed",
        "execution_authority_endpoint": "step_executor",
        "action_type": "runtime_execution",
        "runtime_session": "runtime-session",
        "approval_state": "approved",
        "policy_result": {"allowed": True, "source": source},
        "trace_id": "trace:runtime-task:runtime-step",
    }


def _authority_context(authority: dict) -> dict:
    return {
        "authority_propagation_required": True,
        "execution_authority_granted": True,
        "can_execute_privileged_step": True,
        "execution_authority": authority,
    }


@pytest.mark.parametrize(
    "authority_source",
    ["runtime_dispatcher", "core.runtime.runtime_dispatcher"],
)
def test_runtime_dispatcher_authority_is_accepted_and_sealed_by_step_executor(
    tmp_path: Path, authority_source: str
) -> None:
    result = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {
            "type": "write_file",
            "path": "workspace/shared/runtime-dispatch-accepted.txt",
            "content": "runtime dispatch accepted",
        },
        context={"authority_context": _authority_context(_authority(authority_source))},
    )

    assert result["ok"] is True
    assert result["authority_decision"]["decision"] == "allowed"
    assert result["authority_decision"]["sealed"] is True


def test_taskrunner_propagates_valid_upstream_execution_authority_without_granting() -> None:
    """TaskRunner preserves the runtime-owner grant without claiming it."""
    authority = _authority()
    task = {
        "task_id": "runtime-task",
        "execution_authority": authority,
        "authority_context": {
            "execution_authority": authority,
            "authority_chain": [
                {
                    "layer": "runtime_dispatcher",
                    "execution_authority_granted": True,
                    "can_execute_privileged_step": True,
                }
            ],
        },
    }

    context = TaskRunner()._build_taskrunner_authority_context(
        task=task,
        state={},
        step={"id": "runtime-step", "type": "noop"},
    )

    assert context["execution_authority"] == authority
    assert context["execution_authority_propagated"] is True
    assert context["execution_authority_granted"] is False
    assert context["can_execute_privileged_step"] is False
    assert context["authority_chain"][0]["layer"] == "runtime_dispatcher"
    assert context["authority_chain"][0]["execution_authority_granted"] is True
    assert context["authority_chain"][-1]["layer"] == "task_runner"
    assert context["authority_chain"][-1]["execution_authority_propagated"] is True
    assert context["authority_chain"][-1]["execution_authority_granted"] is False


def test_step_executor_still_blocks_missing_authority(tmp_path: Path) -> None:
    result = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {"type": "noop"},
        context={"authority_propagation_required": True},
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["authority_decision"]["reason"] == "missing_or_invalid_execution_authority"


def test_step_executor_still_blocks_non_allowed_authority_source(tmp_path: Path) -> None:
    authority = _authority("untrusted_runtime_source")
    result = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {"type": "noop"},
        context={"authority_context": _authority_context(authority)},
    )

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["authority_decision"]["reason"] == "missing_or_invalid_execution_authority"


class _Planner:
    def plan(self, **_kwargs):
        return {
            "ok": True,
            "steps": [
                {
                    "id": "runtime-write",
                    "type": "write_file",
                    "path": "workspace/shared/runtime-authority-closure.txt",
                    "content": "done",
                }
            ],
            "meta": {"semantic_type": "multi_step_task"},
        }


def test_work_package_run_passes_execution_authority_gate(tmp_path: Path) -> None:
    queue = RuntimePackageQueue(repo_root=tmp_path)
    dispatcher = RuntimeDispatcher(queue=queue, workspace_root=tmp_path / "workspace")
    operator = RuntimeWorkPackageOperator(
        repo_root=tmp_path,
        queue=queue,
        planner_bridge=WorkPackagePlannerBridge(planner=_Planner()),
        dispatcher=dispatcher,
    )
    operator.submit_package(
        {
            "package_id": "authority-closure-package",
            "title": "Authority closure",
            "goal": "Run through StepExecutor",
            "description": "Exercise runtime-owned WorkPackage authority.",
            "target_files": ["core/runtime/runtime_dispatcher.py"],
            "requirements": ["authority closure"],
            "hard_boundary": ["TaskRunner required", "no direct StepExecutor"],
            "non_mainline_issue_reporting": ["report only"],
            "validation_commands": ["pytest"],
            "completion_report_format": ["runtime progress"],
        }
    )

    result = operator.run_package("authority-closure-package")

    assert result["runtime_lifecycle_state"] == "completed"
    assert "missing_or_invalid_execution_authority" not in str(result)
