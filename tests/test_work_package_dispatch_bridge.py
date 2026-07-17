from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.runtime.execution_package_dispatch_bridge import (
    RUNTIME_DISPATCH_REQUEST_SCHEMA,
    execution_package_to_runtime_dispatch_request,
)
from core.runtime.work_package_operator import RuntimeWorkPackageOperator


ROOT = Path(__file__).resolve().parents[1]


def _payload(package_id: str = "dispatch-bridge-package") -> dict:
    return {
        "package_id": package_id,
        "title": "Dispatch bridge package",
        "goal": "Convert execution package into runtime dispatch request",
        "description": "Prepare dispatcher payload without executing runtime steps.",
        "target_files": ["core/runtime/runtime_dispatcher.py"],
        "requirements": ["dispatch bridge payload"],
        "hard_boundary": ["do not execute"],
        "non_mainline_issue_reporting": {"enabled": True, "mode": "report_all"},
        "validation_commands": [
            "python -m pytest tests/test_work_package_dispatch_bridge.py -q"
        ],
        "completion_report_format": ["dispatch bridge summary"],
    }


def test_bridge_requires_existing_approved_proposal() -> None:
    execution_package = {
        "schema": "zero.work_package.execution_package.v1",
        "package_id": "dispatch-bridge-package",
        "objective": "dispatch",
        "approved_proposal": {
            "proposal_id": "proposal-1",
            "approval": {"approved": False, "mutation_allowed": False},
        },
        "executable_steps": [{"id": "inspect", "type": "read_file"}],
        "validation_commands": [],
        "mutation_allowed": False,
        "required_operator_approval": True,
        "non_mainline_reporting_enabled": True,
    }

    with pytest.raises(PermissionError, match="proposal_approval_required"):
        execution_package_to_runtime_dispatch_request(execution_package)


def test_execution_package_converts_to_runtime_dispatch_request_without_execution(tmp_path: Path) -> None:
    operator = RuntimeWorkPackageOperator(repo_root=tmp_path)
    operator.submit_package(_payload())
    operator.approve_proposal("dispatch-bridge-package")
    execution = operator.execution_package("dispatch-bridge-package")["execution_package"]
    record = operator.queue.status("dispatch-bridge-package")

    request = execution_package_to_runtime_dispatch_request(execution, record=record)

    assert request["schema"] == RUNTIME_DISPATCH_REQUEST_SCHEMA
    assert request["package_id"] == "dispatch-bridge-package"
    assert request["runtime_endpoint"] == "RuntimeDispatcher.dispatch"
    assert request["dispatch_args"] == {"package_id": "dispatch-bridge-package"}
    assert request["runtime_queue_item"]["runtime_owner"] == "RuntimeDispatcher"
    assert request["runtime_queue_item"]["taskrunner_required"] is True
    assert request["runtime_queue_item"]["step_executor_endpoint_only"] is True
    assert request["runtime_queue_item"]["direct_execution"] is False
    assert request["execution_path"]["runtime_owns_execution"] is True
    assert request["execution_path"]["taskrunner_required"] is True
    assert request["execution_path"]["step_executor_endpoint_only"] is True
    assert request["dispatch_payload_only"] is True
    assert request["direct_execution"] is False
    assert request["repo_mutation_performed_by_zero"] is False


def test_operator_records_dispatch_request_and_preserves_package_flags(tmp_path: Path) -> None:
    operator = RuntimeWorkPackageOperator(repo_root=tmp_path)
    operator.submit_package(_payload())
    operator.approve_proposal("dispatch-bridge-package")
    execution = operator.execution_package("dispatch-bridge-package")["execution_package"]

    result = operator.runtime_dispatch_request("dispatch-bridge-package")
    request = result["runtime_dispatch_request"]
    record = operator.queue.status("dispatch-bridge-package")

    assert request["mutation_allowed"] == execution["mutation_allowed"] is False
    assert request["required_operator_approval"] == execution["required_operator_approval"] is True
    assert (
        request["non_mainline_reporting_enabled"]
        == execution["non_mainline_reporting_enabled"]
        is True
    )
    assert record["runtime_dispatch_request"] == request
    assert record["runtime_dispatch_request_summary"]["dispatch_payload_only"] is True
    assert record["runtime_dispatch_request_summary"]["direct_execution"] is False
    assert record["status"] == "queued"
    assert record["runtime_lifecycle_state"] == "planned"


def test_operator_refuses_dispatch_payload_without_approval(tmp_path: Path) -> None:
    operator = RuntimeWorkPackageOperator(repo_root=tmp_path)
    operator.submit_package(_payload())

    with pytest.raises(PermissionError, match="proposal_approval_required"):
        operator.runtime_dispatch_request("dispatch-bridge-package")


def test_dispatch_bridge_does_not_construct_or_call_runtime_execution() -> None:
    source = (ROOT / "core/runtime/execution_package_dispatch_bridge.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)

    forbidden_names = {"RuntimeDispatcher", "TaskRunner", "StepExecutor"}
    assert not [
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id in forbidden_names
    ]
    assert not [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr in {"dispatch", "run_task", "execute_step", "execute_steps"}
    ]
