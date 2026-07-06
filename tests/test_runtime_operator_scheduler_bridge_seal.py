from __future__ import annotations

import inspect
from pathlib import Path

from core.runtime.runtime_operator_scheduler_bridge import (
    RUNTIME_OPERATOR_SCHEDULER_BRIDGE_SCHEMA,
    RuntimeOperatorSchedulerBridge,
    build_scheduler_admission_request,
)


PACKAGE = {
    "schema": "zero.work_package.runtime_intake.v1",
    "package_id": "runtime-operator-scheduler-bridge-seal",
    "task_id": "runtime-operator-scheduler-bridge-seal-task",
    "requested_mode": "controlled",
    "goal": "Seal scheduler admission bridge without direct scheduler queue mutation.",
    "authority_context": {
        "approval": "approved",
        "mode": "controlled",
        "allowed_scope": [
            "core/runtime/runtime_operator_scheduler_bridge.py",
            "tests/test_runtime_operator_scheduler_bridge_seal.py",
        ],
    },
    "requested_changes": [
        {
            "type": "add_runtime_bridge",
            "path": "core/runtime/runtime_operator_scheduler_bridge.py",
            "description": "Prepare scheduler admission without importing scheduler.",
        }
    ],
}


OPERATOR_RESULT = {
    "ok": True,
    "controlled_mutation": True,
    "commit_allowed": True,
    "commit_recorded": True,
    "runtime_commit_apply_status": "git_commit_noop_no_diff",
    "non_mainline_issues": [],
}


def test_scheduler_bridge_prepares_admission_without_scheduler_side_effects() -> None:
    request = build_scheduler_admission_request(
        package=PACKAGE,
        run_id="operator-console-run-test",
        operator_result=OPERATOR_RESULT,
    )

    assert request["schema"] == RUNTIME_OPERATOR_SCHEDULER_BRIDGE_SCHEMA
    assert request["bridge_status"] == "scheduler_admission_prepared"
    assert request["scheduler_ready"] is True
    assert request["scheduler_admission_ready"] is True
    assert request["package_id"] == PACKAGE["package_id"]
    assert request["task_id"] == PACKAGE["task_id"]
    assert request["run_id"] == "operator-console-run-test"
    assert request["authority_context"] == PACKAGE["authority_context"]
    assert request["requested_changes"] == PACKAGE["requested_changes"]
    assert request["operator_ok"] is True
    assert request["operator_controlled_mutation"] is True
    assert request["operator_commit_allowed"] is True
    assert request["operator_commit_recorded"] is True
    assert isinstance(request["non_mainline_issues"], list)

    assert request["scheduler_called"] is False
    assert request["scheduler_imported"] is False
    assert request["queue_mutated"] is False
    assert request["direct_queue_mutation"] is False
    assert request["direct_scheduler_call_performed"] is False


def test_scheduler_bridge_class_delegates_to_data_only_builder() -> None:
    bridge = RuntimeOperatorSchedulerBridge()
    request = bridge.prepare_admission(
        package=PACKAGE,
        run_id="operator-console-run-class",
        operator_result=OPERATOR_RESULT,
    )

    assert request["schema"] == bridge.schema
    assert request["run_id"] == "operator-console-run-class"
    assert bridge.scheduler_imported is False
    assert bridge.queue_mutated is False


def test_scheduler_bridge_blocks_invalid_package_without_queue_mutation() -> None:
    request = build_scheduler_admission_request(
        package={"package_id": "missing-fields"},
        run_id="operator-console-run-invalid",
        operator_result={},
    )

    assert request["scheduler_ready"] is False
    assert request["bridge_status"] == "scheduler_admission_blocked"
    assert "missing_task_id" in request["problems"]
    assert "missing_goal" in request["problems"]
    assert "missing_authority_context" in request["problems"]
    assert "missing_requested_changes" in request["problems"]
    assert request["scheduler_called"] is False
    assert request["queue_mutated"] is False


def test_scheduler_bridge_has_no_scheduler_or_filesystem_mutation_tokens() -> None:
    source = inspect.getsource(__import__(
        "core.runtime.runtime_operator_scheduler_bridge",
        fromlist=["dummy"],
    ))

    forbidden = [
        "from core.tasks",
        "import core.tasks",
        "import scheduler",
        "Scheduler(",
        ".enqueue(",
        ".schedule(",
        ".submit_existing_task(",
        "write_text(",
        "open(",
        "subprocess",
    ]
    leaked = [token for token in forbidden if token in source]
    assert leaked == []


def test_scheduler_bridge_module_path_exists() -> None:
    assert Path("core/runtime/runtime_operator_scheduler_bridge.py").exists()
