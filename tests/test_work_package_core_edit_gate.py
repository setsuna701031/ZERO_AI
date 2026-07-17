from __future__ import annotations

import pytest

from core.tasks.work_package_execution_guard import (
    WorkPackageExecutionRejected,
    validate_execute_request,
    validate_execute_target,
)


def test_core_edit_gate_allows_workspace_targets() -> None:
    assert validate_execute_target("workspace/output.txt") is True


def test_core_edit_gate_allows_work_package_core_files() -> None:
    decision = validate_execute_request(
        {
            "operation": "write_file",
            "target_path": "core/tasks/work_package_intake.py",
        }
    )

    assert decision.ok is True
    assert decision.reason == "allowlisted_core_work_package_target_allowed"


def test_core_edit_gate_blocks_agent_loop() -> None:
    with pytest.raises(WorkPackageExecutionRejected, match="blocked_target_prefix:core/agent"):
        validate_execute_request(
            {
                "operation": "write_file",
                "target_path": "core/agent/agent_loop.py",
            }
        )


def test_core_edit_gate_blocks_runtime_files() -> None:
    with pytest.raises(WorkPackageExecutionRejected, match="blocked_target_prefix:core/runtime"):
        validate_execute_request(
            {
                "operation": "write_file",
                "target_path": "core/runtime/step_executor.py",
            }
        )


def test_core_edit_gate_blocks_scheduler_py() -> None:
    with pytest.raises(WorkPackageExecutionRejected, match="blocked_target_prefix:core/tasks/scheduler.py"):
        validate_execute_request(
            {
                "operation": "write_file",
                "target_path": "core/tasks/scheduler.py",
            }
        )


def test_core_edit_gate_blocks_tests() -> None:
    with pytest.raises(WorkPackageExecutionRejected, match="blocked_target_prefix:tests"):
        validate_execute_request(
            {
                "operation": "write_file",
                "target_path": "tests/test_x.py",
            }
        )


def test_core_edit_gate_blocks_git() -> None:
    with pytest.raises(WorkPackageExecutionRejected, match="blocked_target_prefix:.git"):
        validate_execute_request(
            {
                "operation": "write_file",
                "target_path": ".git/config",
            }
        )


def test_core_edit_gate_blocks_path_escape() -> None:
    with pytest.raises(WorkPackageExecutionRejected, match="path_must_not_escape_repo"):
        validate_execute_request(
            {
                "operation": "write_file",
                "target_path": "../escape.txt",
            }
        )


def test_core_edit_gate_blocks_non_allowlisted_core_tasks_file() -> None:
    with pytest.raises(WorkPackageExecutionRejected, match="target_not_in_execute_allowlist"):
        validate_execute_request(
            {
                "operation": "write_file",
                "target_path": "core/tasks/task_runner.py",
            }
        )
