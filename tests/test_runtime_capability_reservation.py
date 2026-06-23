from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from core.runtime.runtime_capability_reservation import (
    RUNTIME_CAPABILITY_RESERVATION_SCHEMA,
    authority_envelope_to_capability_reservation,
)


ROOT = Path(__file__).resolve().parents[1]


def _authority_envelope() -> dict:
    return {
        "schema": "zero.runtime.authority_envelope.v1",
        "authority_envelope_id": "authority-envelope-123",
        "package_id": "capability-reservation-package",
        "dispatch_contract_id": "runtime-dispatch-contract-123",
        "execution_envelope_id": "runtime-execution-envelope-123",
        "authority_state": "pending",
        "execution_authority": {
            "owner": "RuntimeDispatcher",
            "scope": "execution_package",
            "approved": True,
        },
        "runtime_execution_capability": {"status": "reserved"},
        "mutation_allowed": False,
        "direct_execution": False,
        "authority_payload_only": True,
        "non_mainline_reporting_enabled": True,
        "validation_commands": [
            "python -m pytest tests/test_runtime_capability_reservation.py -q"
        ],
        "source_execution_envelope": {
            "package_id": "capability-reservation-package",
            "validation_commands": ["nested-command"],
        },
    }


def test_capability_reservation_contract_schema() -> None:
    authority_envelope = _authority_envelope()

    reservation = authority_envelope_to_capability_reservation(authority_envelope)

    assert reservation["schema"] == RUNTIME_CAPABILITY_RESERVATION_SCHEMA
    assert reservation["reservation_id"].startswith("runtime-capability-reservation-")
    assert reservation["package_id"] == "capability-reservation-package"
    assert reservation["authority_envelope_id"] == "authority-envelope-123"
    assert reservation["runtime_owner"] == "RuntimeDispatcher"
    assert reservation["execution_authority"] == {
        "approved": True,
        "scope": "execution_package",
    }
    assert reservation["runtime_execution_capability"] == {"status": "reserved"}
    assert reservation["capability_scope"] == {
        "taskrunner_required": True,
        "step_executor_endpoint_only": True,
    }
    assert reservation["mutation_allowed"] is False
    assert reservation["direct_execution"] is False
    assert reservation["reservation_payload_only"] is True
    assert reservation["non_mainline_reporting_enabled"] is True
    assert reservation["validation_commands"] == [
        "python -m pytest tests/test_runtime_capability_reservation.py -q"
    ]
    assert reservation["source_authority_envelope"] == authority_envelope


def test_capability_reservation_deep_copy_protection() -> None:
    authority_envelope = _authority_envelope()
    reservation = authority_envelope_to_capability_reservation(authority_envelope)
    expected_source = copy.deepcopy(authority_envelope)
    expected_commands = copy.deepcopy(authority_envelope["validation_commands"])

    authority_envelope["source_execution_envelope"]["changed"] = True
    authority_envelope["validation_commands"].append("changed-command")

    assert reservation["source_authority_envelope"] == expected_source
    assert reservation["validation_commands"] == expected_commands


@pytest.mark.parametrize(
    ("field_path", "value", "match"),
    [
        (("execution_authority", "approved"), False, "approval_required"),
        (("authority_payload_only",), False, "payload_only_required"),
        (("mutation_allowed",), True, "mutation_must_be_false"),
        (("direct_execution",), True, "direct_execution_must_be_false"),
    ],
)
def test_capability_reservation_approval_gate(
    field_path: tuple[str, ...], value: object, match: str
) -> None:
    authority_envelope = _authority_envelope()
    target = authority_envelope
    for field in field_path[:-1]:
        target = target[field]
    target[field_path[-1]] = value

    with pytest.raises(PermissionError, match=match):
        authority_envelope_to_capability_reservation(authority_envelope)


def test_capability_reservation_reserved_state() -> None:
    reservation = authority_envelope_to_capability_reservation(_authority_envelope())

    assert reservation["reservation_state"] == "reserved"
    assert reservation["runtime_execution_capability"]["status"] == "reserved"


def test_capability_reservation_source_has_no_forbidden_runtime_imports() -> None:
    source = (ROOT / "core/runtime/runtime_capability_reservation.py").read_text(
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


def test_capability_reservation_source_has_no_forbidden_runtime_calls() -> None:
    source = (ROOT / "core/runtime/runtime_capability_reservation.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)

    assert not [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr in {"dispatch", "run_task", "execute_step", "execute_steps"}
    ]
