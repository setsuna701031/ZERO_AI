from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.runtime.runtime_authority_context import (
    RUNTIME_AUTHORITY_CONTEXT_SCHEMA,
    execution_authority_token_to_context,
)


ROOT = Path(__file__).resolve().parents[1]


def _token() -> dict:
    return {
        "schema": "zero.runtime.execution_authority_token.v1",
        "token_id": "token-1",
        "package_id": "package-1",
        "authority_state": "issued",
        "runtime_owner": "RuntimeDispatcher",
        "execution_authority": {
            "owner": "RuntimeDispatcher",
            "scope": "execution_package",
            "approved": True,
        },
        "runtime_execution_capability": {
            "status": "reserved",
            "capability_id": "capability-1",
        },
        "capability_token": {
            "state": "issued",
            "live_execution": False,
        },
        "mutation_allowed": False,
        "direct_execution": False,
        "authority_payload_only": True,
        "validation_commands": ["python -m pytest tests/test_runtime_authority_context.py -q"],
        "non_mainline_reporting_enabled": True,
    }


def test_execution_authority_token_converts_to_authority_context() -> None:
    context = execution_authority_token_to_context(_token())

    assert context["schema"] == RUNTIME_AUTHORITY_CONTEXT_SCHEMA
    assert context["package_id"] == "package-1"
    assert context["authority_token_id"] == "token-1"
    assert context["authority_owner"] == "RuntimeDispatcher"
    assert context["authority_scope"] == "execution_package"
    assert context["authority_state"] == "issued"
    assert context["runtime_execution_capability"]["status"] == "reserved"
    assert context["mutation_allowed"] is False
    assert context["direct_execution"] is False
    assert context["authority_payload_only"] is True
    assert context["non_mainline_reporting_enabled"] is True
    assert context["validation_commands"] == [
        "python -m pytest tests/test_runtime_authority_context.py -q"
    ]


def test_authority_context_deep_copies_source_token() -> None:
    token = _token()
    context = execution_authority_token_to_context(token)

    token["runtime_execution_capability"]["status"] = "mutated"
    token["validation_commands"].append("mutated")

    assert context["runtime_execution_capability"]["status"] == "reserved"
    assert context["source_authority_token"]["runtime_execution_capability"]["status"] == "reserved"
    assert context["validation_commands"] == [
        "python -m pytest tests/test_runtime_authority_context.py -q"
    ]


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("authority_payload_only", False, "authority_payload_only_required"),
        ("authority_state", "reserved", "authority_token_issued_required"),
        ("mutation_allowed", True, "mutation_not_allowed"),
        ("direct_execution", True, "direct_execution_not_allowed"),
    ],
)
def test_authority_context_rejects_unsafe_token_state(
    field: str,
    value: object,
    reason: str,
) -> None:
    token = _token()
    token[field] = value

    with pytest.raises(PermissionError, match=reason):
        execution_authority_token_to_context(token)


def test_authority_context_rejects_unapproved_execution_authority() -> None:
    token = _token()
    token["execution_authority"]["approved"] = False

    with pytest.raises(PermissionError, match="execution_authority_approval_required"):
        execution_authority_token_to_context(token)


def test_authority_context_accepts_capability_token_issued_state() -> None:
    token = _token()
    token.pop("authority_state")
    token["capability_token"]["state"] = "issued"

    context = execution_authority_token_to_context(token)

    assert context["authority_state"] == "issued"


def test_authority_context_source_has_no_runtime_executor_imports_or_calls() -> None:
    source = (ROOT / "core/runtime/runtime_authority_context.py").read_text(
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