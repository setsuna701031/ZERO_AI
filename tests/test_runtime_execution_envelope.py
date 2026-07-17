from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from core.runtime.runtime_execution_envelope import (
    RUNTIME_EXECUTION_ENVELOPE_SCHEMA,
    dispatch_contract_to_execution_envelope,
)


ROOT = Path(__file__).resolve().parents[1]


def _contract() -> dict:
    return {
        "schema": "zero.runtime.dispatch_contract.v1",
        "package_id": "execution-envelope-package",
        "dispatch_request_id": "runtime-dispatch-request-123",
        "runtime_owner": "RuntimeDispatcher",
        "taskrunner_required": True,
        "step_executor_endpoint_only": True,
        "mutation_allowed": False,
        "direct_execution": False,
        "dispatch_payload_only": True,
        "non_mainline_reporting_enabled": True,
        "validation_commands": [
            "python -m pytest tests/test_runtime_execution_envelope.py -q"
        ],
        "runtime_queue_item": {
            "package_id": "execution-envelope-package",
            "steps": [{"id": "inspect", "type": "read_file"}],
            "runtime_owner": "RuntimeDispatcher",
            "taskrunner_required": True,
            "step_executor_endpoint_only": True,
            "direct_execution": False,
            "dispatch_payload_only": True,
        },
        "source_dispatch_request": {"package_id": "execution-envelope-package"},
    }


def test_dispatch_contract_converts_to_execution_envelope() -> None:
    contract = _contract()

    envelope = dispatch_contract_to_execution_envelope(contract)

    assert envelope["schema"] == RUNTIME_EXECUTION_ENVELOPE_SCHEMA
    assert envelope["package_id"] == "execution-envelope-package"
    assert envelope["dispatch_contract_id"] == "runtime-dispatch-request-123"
    assert envelope["runtime_owner"] == "RuntimeDispatcher"
    assert envelope["taskrunner_required"] is True
    assert envelope["step_executor_endpoint_only"] is True
    assert envelope["mutation_allowed"] is False
    assert envelope["direct_execution"] is False
    assert envelope["dispatch_payload_only"] is True
    assert envelope["execution_authority"] == "pending"
    assert envelope["runtime_execution_capability"] == "pending"
    assert envelope["source_dispatch_contract"] == contract


def test_envelope_rejects_mutation_allowed_true() -> None:
    contract = _contract()
    contract["mutation_allowed"] = True

    with pytest.raises(PermissionError, match="mutation_must_be_false"):
        dispatch_contract_to_execution_envelope(contract)


def test_envelope_rejects_direct_execution_true() -> None:
    contract = _contract()
    contract["direct_execution"] = True

    with pytest.raises(PermissionError, match="direct_execution_must_be_false"):
        dispatch_contract_to_execution_envelope(contract)


def test_envelope_requires_payload_only_contract() -> None:
    contract = _contract()
    contract["dispatch_payload_only"] = False

    with pytest.raises(PermissionError, match="payload_only_required"):
        dispatch_contract_to_execution_envelope(contract)


def test_envelope_preserves_validation_and_non_mainline_flags() -> None:
    contract = _contract()
    contract["validation_commands"] = ["cmd-a", "cmd-b"]
    contract["non_mainline_reporting_enabled"] = False

    envelope = dispatch_contract_to_execution_envelope(contract)

    assert envelope["validation_commands"] == ["cmd-a", "cmd-b"]
    assert envelope["non_mainline_reporting_enabled"] is False
    assert envelope["source_dispatch_contract"]["validation_commands"] == ["cmd-a", "cmd-b"]
    assert envelope["source_dispatch_contract"]["non_mainline_reporting_enabled"] is False


def test_envelope_does_not_alias_source_contract() -> None:
    contract = _contract()
    envelope = dispatch_contract_to_execution_envelope(contract)
    contract_copy = copy.deepcopy(contract)

    contract["runtime_queue_item"]["steps"].append({"id": "changed", "type": "inspect"})

    assert envelope["source_dispatch_contract"] == contract_copy


def test_source_has_no_runtime_executor_imports_or_calls() -> None:
    source = (ROOT / "core/runtime/runtime_execution_envelope.py").read_text(
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
