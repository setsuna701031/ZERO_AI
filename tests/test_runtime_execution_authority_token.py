from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from core.runtime.runtime_execution_authority_token import (
    RUNTIME_EXECUTION_AUTHORITY_TOKEN_SCHEMA,
    capability_reservation_to_execution_authority_token,
)


ROOT = Path(__file__).resolve().parents[1]


def _reservation() -> dict:
    return {
        "schema": "zero.runtime.capability_reservation.v1",
        "reservation_id": "reservation-123",
        "package_id": "authority-token-package",
        "authority_envelope_id": "authority-envelope-123",
        "reservation_state": "reserved",
        "runtime_owner": "RuntimeDispatcher",
        "execution_authority": {
            "approved": True,
            "scope": "execution_package",
        },
        "runtime_execution_capability": {
            "status": "reserved",
        },
        "capability_scope": {
            "taskrunner_required": True,
            "step_executor_endpoint_only": True,
        },
        "mutation_allowed": False,
        "direct_execution": False,
        "reservation_payload_only": True,
        "non_mainline_reporting_enabled": True,
        "validation_commands": [
            "python -m pytest tests/test_runtime_execution_authority_token.py -q"
        ],
        "source_authority_envelope": {
            "authority_envelope_id": "authority-envelope-123",
            "package_id": "authority-token-package",
        },
    }


def test_execution_authority_token_contract_schema() -> None:
    reservation = _reservation()

    token = capability_reservation_to_execution_authority_token(reservation)

    assert token["schema"] == RUNTIME_EXECUTION_AUTHORITY_TOKEN_SCHEMA
    assert token["execution_authority_token_id"].startswith(
        "runtime-execution-authority-token-"
    )
    assert token["reservation_id"] == "reservation-123"
    assert token["package_id"] == "authority-token-package"
    assert token["authority_envelope_id"] == "authority-envelope-123"
    assert token["token_state"] == "issued"
    assert token["runtime_owner"] == "RuntimeDispatcher"
    assert token["execution_authority"] == {
        "approved": True,
        "scope": "execution_package",
        "tokenized": True,
    }
    assert token["runtime_execution_capability"] == {
        "status": "authority_token_issued",
        "source_status": "reserved",
    }
    assert token["capability_scope"] == {
        "taskrunner_required": True,
        "step_executor_endpoint_only": True,
    }
    assert token["mutation_allowed"] is False
    assert token["direct_execution"] is False
    assert token["runtime_execution_performed"] is False
    assert token["authority_token_payload_only"] is True
    assert token["non_mainline_reporting_enabled"] is True
    assert token["validation_commands"] == [
        "python -m pytest tests/test_runtime_execution_authority_token.py -q"
    ]
    assert token["source_capability_reservation"] == reservation


def test_execution_authority_token_preserves_existing_token_id() -> None:
    reservation = _reservation()
    reservation["execution_authority_token_id"] = "authority-token-existing"

    token = capability_reservation_to_execution_authority_token(reservation)

    assert token["execution_authority_token_id"] == "authority-token-existing"


def test_execution_authority_token_deep_copy_protection() -> None:
    reservation = _reservation()
    token = capability_reservation_to_execution_authority_token(reservation)
    expected_source = copy.deepcopy(reservation)
    expected_commands = copy.deepcopy(reservation["validation_commands"])

    reservation["source_authority_envelope"]["changed"] = True
    reservation["validation_commands"].append("changed-command")

    assert token["source_capability_reservation"] == expected_source
    assert token["validation_commands"] == expected_commands


@pytest.mark.parametrize(
    ("field_path", "value", "match"),
    [
        (("reservation_state",), "pending", "reserved_state_required"),
        (("execution_authority", "approved"), False, "approval_required"),
        (("reservation_payload_only",), False, "payload_only_required"),
        (("mutation_allowed",), True, "mutation_must_be_false"),
        (("direct_execution",), True, "direct_execution_must_be_false"),
        (
            ("runtime_execution_capability", "status"),
            "missing",
            "capability_reserved_required",
        ),
        (("capability_scope", "taskrunner_required"), False, "taskrunner_required"),
        (
            ("capability_scope", "step_executor_endpoint_only"),
            False,
            "step_executor_endpoint_only",
        ),
    ],
)
def test_execution_authority_token_gate(
    field_path: tuple[str, ...], value: object, match: str
) -> None:
    reservation = _reservation()
    target = reservation
    for field in field_path[:-1]:
        target = target[field]
    target[field_path[-1]] = value

    with pytest.raises(PermissionError, match=match):
        capability_reservation_to_execution_authority_token(reservation)


def test_execution_authority_token_requires_lineage_ids() -> None:
    reservation = _reservation()
    reservation["reservation_id"] = ""

    with pytest.raises(ValueError, match="reservation_id_required"):
        capability_reservation_to_execution_authority_token(reservation)

    reservation = _reservation()
    reservation["authority_envelope_id"] = ""

    with pytest.raises(ValueError, match="authority_envelope_id_required"):
        capability_reservation_to_execution_authority_token(reservation)


def test_execution_authority_token_source_has_no_forbidden_runtime_imports() -> None:
    source = (ROOT / "core/runtime/runtime_execution_authority_token.py").read_text(
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


def test_execution_authority_token_source_has_no_forbidden_runtime_calls() -> None:
    source = (ROOT / "core/runtime/runtime_execution_authority_token.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)

    assert not [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr in {"dispatch", "run_task", "execute_step"}
    ]
