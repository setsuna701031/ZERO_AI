from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from core.runtime.runtime_dispatch_contract import (
    RUNTIME_DISPATCH_CONTRACT_SCHEMA,
    runtime_dispatch_request_to_contract,
)


ROOT = Path(__file__).resolve().parents[1]


def _dispatch_request() -> dict:
    return {
        "schema": "zero.work_package.runtime_dispatch_request.v1",
        "package_id": "dispatch-contract-package",
        "task_id": "task-dispatch-contract-package",
        "session_id": "session-1",
        "approved_proposal": {
            "proposal_id": "proposal-1",
            "approval": {
                "package_id": "dispatch-contract-package",
                "proposal_id": "proposal-1",
                "approved": True,
                "approved_by": "operator",
                "approved_at": "2026-06-23T00:00:00+00:00",
                "approval_scope": "execution_package_generation",
                "mutation_allowed": False,
            },
        },
        "approval": {
            "package_id": "dispatch-contract-package",
            "proposal_id": "proposal-1",
            "approved": True,
            "approved_by": "operator",
            "approved_at": "2026-06-23T00:00:00+00:00",
            "approval_scope": "execution_package_generation",
            "mutation_allowed": False,
        },
        "runtime_queue_item": {
            "package_id": "dispatch-contract-package",
            "task_id": "task-dispatch-contract-package",
            "session_id": "session-1",
            "status": "queued",
            "lifecycle_state": "queued",
            "steps": [{"id": "inspect", "type": "read_file"}],
            "runtime_owner": "RuntimeDispatcher",
            "taskrunner_required": True,
            "step_executor_endpoint_only": True,
            "direct_execution": False,
        },
        "executable_steps": [{"id": "inspect", "type": "read_file"}],
        "validation_commands": ["python -m pytest tests/test_runtime_dispatch_contract.py -q"],
        "mutation_allowed": False,
        "required_operator_approval": True,
        "non_mainline_reporting_enabled": True,
        "dispatch_payload_only": True,
        "direct_execution": False,
        "repo_mutation_performed_by_zero": False,
    }


def test_approved_dispatch_request_can_convert_to_contract() -> None:
    request = _dispatch_request()

    contract = runtime_dispatch_request_to_contract(request)

    assert contract["schema"] == RUNTIME_DISPATCH_CONTRACT_SCHEMA
    assert contract["package_id"] == "dispatch-contract-package"
    assert contract["dispatch_request_id"].startswith("runtime-dispatch-request-")
    assert contract["runtime_owner"] == "RuntimeDispatcher"
    assert contract["taskrunner_required"] is True
    assert contract["step_executor_endpoint_only"] is True
    assert contract["mutation_allowed"] is False
    assert contract["direct_execution"] is False
    assert contract["dispatch_payload_only"] is True
    assert contract["source_dispatch_request"] == request
    assert contract["runtime_queue_item"]["runtime_owner"] == "RuntimeDispatcher"
    assert contract["runtime_queue_item"]["taskrunner_required"] is True
    assert contract["runtime_queue_item"]["step_executor_endpoint_only"] is True
    assert contract["runtime_queue_item"]["direct_execution"] is False


def test_mutation_allowed_true_is_rejected() -> None:
    request = _dispatch_request()
    request["mutation_allowed"] = True

    with pytest.raises(PermissionError, match="mutation_must_be_false"):
        runtime_dispatch_request_to_contract(request)


def test_direct_execution_true_is_rejected() -> None:
    request = _dispatch_request()
    request["direct_execution"] = True

    with pytest.raises(PermissionError, match="direct_execution_must_be_false"):
        runtime_dispatch_request_to_contract(request)


def test_unapproved_dispatch_request_is_rejected() -> None:
    request = _dispatch_request()
    request["approval"] = {**request["approval"], "approved": False}

    with pytest.raises(PermissionError, match="requires_approved_proposal"):
        runtime_dispatch_request_to_contract(request)


def test_contract_preserves_validation_and_non_mainline_flags() -> None:
    request = _dispatch_request()
    request["validation_commands"] = ["cmd-a", "cmd-b"]
    request["non_mainline_reporting_enabled"] = False

    contract = runtime_dispatch_request_to_contract(request)

    assert contract["validation_commands"] == ["cmd-a", "cmd-b"]
    assert contract["non_mainline_reporting_enabled"] is False
    assert contract["source_dispatch_request"]["validation_commands"] == ["cmd-a", "cmd-b"]
    assert contract["source_dispatch_request"]["non_mainline_reporting_enabled"] is False


def test_contract_does_not_alias_source_request() -> None:
    request = _dispatch_request()
    contract = runtime_dispatch_request_to_contract(request)
    request_copy = copy.deepcopy(request)

    request["runtime_queue_item"]["steps"].append({"id": "changed", "type": "inspect"})

    assert contract["source_dispatch_request"] == request_copy
    assert contract["runtime_queue_item"]["steps"] == request_copy["runtime_queue_item"]["steps"]


def test_source_has_no_runtime_executor_imports_or_calls() -> None:
    source = (ROOT / "core/runtime/runtime_dispatch_contract.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    forbidden_imports = {
        "core.runtime.runtime_dispatcher",
        "core.runtime.task_runner",
        "core.runtime.step_executor",
    }
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }

    assert not (forbidden_imports & imported_modules)
    assert not ({"RuntimeDispatcher", "TaskRunner", "StepExecutor"} & imported_names)
    assert not [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr in {"dispatch", "run_task", "execute_step", "execute_steps"}
    ]
