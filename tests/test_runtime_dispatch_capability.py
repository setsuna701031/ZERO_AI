from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.runtime.runtime_dispatch_capability import (
    RUNTIME_DISPATCH_CAPABILITY_SCHEMA,
    authority_context_to_dispatch_capability,
)


ROOT = Path(__file__).resolve().parents[1]


def _context() -> dict:
    return {
        "schema": "zero.runtime.authority_context.v1",
        "authority_context_id": "context-1",
        "package_id": "package-1",
        "authority_owner": "RuntimeDispatcher",
        "authority_scope": "execution_package",
        "authority_token_id": "token-1",
        "authority_state": "issued",
        "runtime_execution_capability": {
            "status": "reserved",
            "capability_id": "capability-1",
        },
        "mutation_allowed": False,
        "direct_execution": False,
        "authority_payload_only": True,
        "validation_commands": ["python -m pytest tests/test_runtime_dispatch_capability.py -q"],
        "non_mainline_reporting_enabled": True,
    }


def test_authority_context_converts_to_dispatch_capability() -> None:
    capability = authority_context_to_dispatch_capability(_context())

    assert capability["schema"] == RUNTIME_DISPATCH_CAPABILITY_SCHEMA
    assert capability["package_id"] == "package-1"
    assert capability["authority_context_id"] == "context-1"
    assert capability["runtime_owner"] == "RuntimeDispatcher"
    assert capability["capability_state"] == "issued"
    assert capability["dispatch_allowed"] is True
    assert capability["taskrunner_required"] is True
    assert capability["step_executor_endpoint_only"] is True
    assert capability["mutation_allowed"] is False
    assert capability["direct_execution"] is False
    assert capability["capability_payload_only"] is True
    assert capability["non_mainline_reporting_enabled"] is True
    assert capability["validation_commands"] == [
        "python -m pytest tests/test_runtime_dispatch_capability.py -q"
    ]


def test_dispatch_capability_deep_copies_source_context() -> None:
    context = _context()
    capability = authority_context_to_dispatch_capability(context)

    context["runtime_execution_capability"]["status"] = "mutated"
    context["validation_commands"].append("mutated")

    assert capability["source_authority_context"]["runtime_execution_capability"]["status"] == "reserved"
    assert capability["validation_commands"] == [
        "python -m pytest tests/test_runtime_dispatch_capability.py -q"
    ]


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("authority_state", "pending", "authority_context_issued_required"),
        ("authority_payload_only", False, "authority_payload_only_required"),
        ("mutation_allowed", True, "mutation_not_allowed"),
        ("direct_execution", True, "direct_execution_not_allowed"),
    ],
)
def test_dispatch_capability_rejects_unsafe_context_state(
    field: str,
    value: object,
    reason: str,
) -> None:
    context = _context()
    context[field] = value

    with pytest.raises(PermissionError, match=reason):
        authority_context_to_dispatch_capability(context)


def test_dispatch_capability_rejects_unreserved_runtime_capability() -> None:
    context = _context()
    context["runtime_execution_capability"]["status"] = "pending"

    with pytest.raises(PermissionError, match="runtime_execution_capability_reserved_required"):
        authority_context_to_dispatch_capability(context)


def test_dispatch_capability_rejects_wrong_schema() -> None:
    context = _context()
    context["schema"] = "wrong.schema"

    with pytest.raises(PermissionError, match="authority_context_schema_required"):
        authority_context_to_dispatch_capability(context)


def test_dispatch_capability_source_has_no_runtime_executor_imports_or_calls() -> None:
    source = (ROOT / "core/runtime/runtime_dispatch_capability.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)

    forbidden_imports = {"RuntimeDispatcher", "TaskRunner", "StepExecutor"}
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not (imported_names & forbidden_imports)

    forbidden_calls = {"dispatch", "run_task", "execute_step", "execute_steps"}
    assert not [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in forbidden_calls
    ]