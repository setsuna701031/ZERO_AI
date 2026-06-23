from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from core.runtime.runtime_authority_envelope import (
    RUNTIME_AUTHORITY_ENVELOPE_SCHEMA,
    execution_envelope_to_authority_envelope,
)


ROOT = Path(__file__).resolve().parents[1]


def _envelope() -> dict:
    return {
        "schema": "zero.runtime.execution_envelope.v1",
        "package_id": "authority-envelope-package",
        "dispatch_contract_id": "runtime-dispatch-contract-123",
        "runtime_owner": "RuntimeDispatcher",
        "taskrunner_required": True,
        "step_executor_endpoint_only": True,
        "mutation_allowed": False,
        "direct_execution": False,
        "dispatch_payload_only": True,
        "validation_commands": [
            "python -m pytest tests/test_runtime_authority_envelope.py -q"
        ],
        "non_mainline_reporting_enabled": True,
        "execution_authority": "pending",
        "runtime_execution_capability": "pending",
        "source_dispatch_contract": {"package_id": "authority-envelope-package"},
    }


def test_execution_envelope_converts_to_authority_envelope() -> None:
    envelope = _envelope()

    authority = execution_envelope_to_authority_envelope(envelope)

    assert authority["schema"] == RUNTIME_AUTHORITY_ENVELOPE_SCHEMA
    assert authority["package_id"] == "authority-envelope-package"
    assert authority["dispatch_contract_id"] == "runtime-dispatch-contract-123"
    assert authority["execution_envelope_id"].startswith("runtime-execution-envelope-")
    assert authority["authority_state"] == "pending"
    assert authority["execution_authority"] == {
        "owner": "RuntimeDispatcher",
        "scope": "execution_package",
        "approved": True,
    }
    assert authority["runtime_execution_capability"] == {"status": "reserved"}
    assert authority["mutation_allowed"] is False
    assert authority["direct_execution"] is False
    assert authority["authority_payload_only"] is True
    assert authority["source_execution_envelope"] == envelope


def test_authority_envelope_preserves_existing_execution_envelope_id() -> None:
    envelope = _envelope()
    envelope["execution_envelope_id"] = "execution-envelope-existing"

    authority = execution_envelope_to_authority_envelope(envelope)

    assert authority["execution_envelope_id"] == "execution-envelope-existing"


def test_authority_envelope_rejects_mutation_allowed_true() -> None:
    envelope = _envelope()
    envelope["mutation_allowed"] = True

    with pytest.raises(PermissionError, match="mutation_must_be_false"):
        execution_envelope_to_authority_envelope(envelope)


def test_authority_envelope_rejects_direct_execution_true() -> None:
    envelope = _envelope()
    envelope["direct_execution"] = True

    with pytest.raises(PermissionError, match="direct_execution_must_be_false"):
        execution_envelope_to_authority_envelope(envelope)


def test_authority_envelope_requires_payload_only_input() -> None:
    envelope = _envelope()
    envelope["dispatch_payload_only"] = False

    with pytest.raises(PermissionError, match="payload_only_required"):
        execution_envelope_to_authority_envelope(envelope)


def test_authority_envelope_does_not_alias_source_envelope() -> None:
    envelope = _envelope()
    authority = execution_envelope_to_authority_envelope(envelope)
    envelope_copy = copy.deepcopy(envelope)

    envelope["source_dispatch_contract"]["changed"] = True

    assert authority["source_execution_envelope"] == envelope_copy


def test_source_has_no_runtime_executor_imports_or_calls() -> None:
    source = (ROOT / "core/runtime/runtime_authority_envelope.py").read_text(
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
