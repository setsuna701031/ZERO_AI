from __future__ import annotations

from core.runtime.contracts.authority_context_contract import (
    AUTHORITY_CONTEXT_SCHEMA,
    validate_authority_context_shape,
)
from core.runtime.contracts.runtime_boundary_contract import (
    RUNTIME_BOUNDARY_SCHEMA,
    normalize_boundary_direction,
    validate_runtime_boundary_shape,
)
from core.runtime.contracts.runtime_execution_contract import (
    RUNTIME_EXECUTION_SCHEMA,
    normalize_runtime_execution_mode,
    validate_runtime_execution_shape,
)
from core.runtime.contracts.runtime_identity_contract import (
    RUNTIME_IDENTITY_SCHEMA,
    validate_runtime_identity_shape,
)
from core.runtime.contracts.runtime_session_contract import (
    RUNTIME_SESSION_SCHEMA,
    is_runtime_session_active_status,
    is_runtime_session_terminal_status,
    normalize_runtime_session_status,
    validate_runtime_session_shape,
)


def test_authority_context_contract_accepts_valid_shape() -> None:
    payload = {
        "authority_phase": "runtime_dispatch",
        "authority_layer": "runtime",
        "authority_role": "runtime_owner",
        "authority_source": "runtime_dispatcher",
        "authority_policy": "owner_issued_runtime_execution_capability",
        "authority_propagation_required": True,
        "execution_authority_granted": True,
        "can_execute_privileged_step": True,
        "received_authority": {},
        "execution_authority": {},
        "authority_chain": [],
    }

    result = validate_authority_context_shape(payload)

    assert result == {
        "ok": True,
        "schema": AUTHORITY_CONTEXT_SCHEMA,
        "reason": "authority_context_shape_valid",
    }


def test_authority_context_contract_rejects_missing_required_field() -> None:
    result = validate_authority_context_shape(
        {
            "authority_phase": "runtime_dispatch",
            "authority_layer": "runtime",
            "authority_role": "runtime_owner",
            "authority_source": "runtime_dispatcher",
            "authority_policy": "owner_issued_runtime_execution_capability",
            "authority_propagation_required": True,
            "execution_authority_granted": True,
            "can_execute_privileged_step": True,
        }
    )

    assert result["ok"] is False
    assert result["schema"] == AUTHORITY_CONTEXT_SCHEMA
    assert result["reason"] == "authority_context_missing_required_fields"
    assert result["missing_fields"] == ["authority_chain"]


def test_authority_context_contract_rejects_invalid_boolean_field() -> None:
    payload = {
        "authority_phase": "runtime_dispatch",
        "authority_layer": "runtime",
        "authority_role": "runtime_owner",
        "authority_source": "runtime_dispatcher",
        "authority_policy": "owner_issued_runtime_execution_capability",
        "authority_propagation_required": "yes",
        "execution_authority_granted": True,
        "can_execute_privileged_step": True,
        "authority_chain": [],
    }

    result = validate_authority_context_shape(payload)

    assert result["ok"] is False
    assert result["reason"] == "authority_context_invalid_boolean_fields"
    assert result["invalid_fields"] == ["authority_propagation_required"]


def test_runtime_identity_contract_accepts_minimal_identity() -> None:
    result = validate_runtime_identity_shape(
        {
            "session_id": "session-1",
            "runtime_session_id": "runtime-session-1",
        }
    )

    assert result == {
        "ok": True,
        "schema": RUNTIME_IDENTITY_SCHEMA,
        "reason": "runtime_identity_shape_valid",
    }


def test_runtime_identity_contract_rejects_missing_runtime_session_id() -> None:
    result = validate_runtime_identity_shape({"session_id": "session-1"})

    assert result["ok"] is False
    assert result["schema"] == RUNTIME_IDENTITY_SCHEMA
    assert result["reason"] == "runtime_identity_missing_required_fields"
    assert result["missing_fields"] == ["runtime_session_id"]


def test_runtime_identity_contract_rejects_non_string_known_field() -> None:
    result = validate_runtime_identity_shape(
        {
            "session_id": "session-1",
            "runtime_session_id": "runtime-session-1",
            "branch_id": 123,
        }
    )

    assert result["ok"] is False
    assert result["reason"] == "runtime_identity_invalid_string_fields"
    assert result["invalid_fields"] == ["branch_id"]


def test_runtime_session_contract_normalizes_status_aliases() -> None:
    assert normalize_runtime_session_status("success") == "finished"
    assert normalize_runtime_session_status("completed") == "finished"
    assert normalize_runtime_session_status("pending") == "queued"
    assert normalize_runtime_session_status("in_progress") == "running"


def test_runtime_session_contract_classifies_active_and_terminal_statuses() -> None:
    assert is_runtime_session_active_status("running") is True
    assert is_runtime_session_active_status("success") is False
    assert is_runtime_session_terminal_status("success") is True
    assert is_runtime_session_terminal_status("running") is False


def test_runtime_session_contract_accepts_valid_session() -> None:
    result = validate_runtime_session_shape(
        {
            "session_id": "session-1",
            "runtime_session_id": "runtime-session-1",
            "status": "success",
        }
    )

    assert result["ok"] is True
    assert result["schema"] == RUNTIME_SESSION_SCHEMA
    assert result["reason"] == "runtime_session_shape_valid"
    assert result["normalized_status"] == "finished"
    assert result["terminal"] is True


def test_runtime_session_contract_rejects_unknown_status() -> None:
    result = validate_runtime_session_shape(
        {
            "session_id": "session-1",
            "runtime_session_id": "runtime-session-1",
            "status": "mystery",
        }
    )

    assert result["ok"] is False
    assert result["schema"] == RUNTIME_SESSION_SCHEMA
    assert result["reason"] == "runtime_session_unknown_status"
    assert result["status"] == "mystery"


def test_runtime_execution_contract_normalizes_mode() -> None:
    assert normalize_runtime_execution_mode("execute") == "execute"
    assert normalize_runtime_execution_mode("replay") == "replay"
    assert normalize_runtime_execution_mode("audit") == "audit"
    assert normalize_runtime_execution_mode("repair_replay") == "repair_replay"
    assert normalize_runtime_execution_mode("unknown") == "execute"


def test_runtime_execution_contract_accepts_valid_execution() -> None:
    result = validate_runtime_execution_shape(
        {
            "execution_id": "execution-1",
            "session_id": "session-1",
            "runtime_session_id": "runtime-session-1",
            "task_id": "task-1",
            "execution_mode": "audit",
            "execution_authority": {},
            "authority_context": {},
            "runtime_identity": {},
        }
    )

    assert result["ok"] is True
    assert result["schema"] == RUNTIME_EXECUTION_SCHEMA
    assert result["reason"] == "runtime_execution_shape_valid"
    assert result["normalized_execution_mode"] == "audit"


def test_runtime_execution_contract_rejects_invalid_mapping_field() -> None:
    result = validate_runtime_execution_shape(
        {
            "execution_id": "execution-1",
            "session_id": "session-1",
            "runtime_session_id": "runtime-session-1",
            "task_id": "task-1",
            "execution_authority": "allowed",
        }
    )

    assert result["ok"] is False
    assert result["schema"] == RUNTIME_EXECUTION_SCHEMA
    assert result["reason"] == "runtime_execution_invalid_mapping_fields"
    assert result["invalid_fields"] == ["execution_authority"]


def test_runtime_boundary_contract_normalizes_direction() -> None:
    assert normalize_boundary_direction("scheduler", "task_runner") == "scheduler->task_runner"


def test_runtime_boundary_contract_accepts_known_direction() -> None:
    result = validate_runtime_boundary_shape(
        {
            "source_component": "scheduler",
            "target_component": "task_runner",
            "boundary_direction": "scheduler->task_runner",
        }
    )

    assert result == {
        "ok": True,
        "schema": RUNTIME_BOUNDARY_SCHEMA,
        "reason": "runtime_boundary_shape_valid",
    }


def test_runtime_boundary_contract_rejects_direction_mismatch() -> None:
    result = validate_runtime_boundary_shape(
        {
            "source_component": "scheduler",
            "target_component": "task_runner",
            "boundary_direction": "task_runner->scheduler",
        }
    )

    assert result["ok"] is False
    assert result["schema"] == RUNTIME_BOUNDARY_SCHEMA
    assert result["reason"] == "runtime_boundary_direction_mismatch"
    assert result["expected_direction"] == "scheduler->task_runner"
    assert result["actual_direction"] == "task_runner->scheduler"


def test_runtime_boundary_contract_rejects_unknown_component() -> None:
    result = validate_runtime_boundary_shape(
        {
            "source_component": "scheduler",
            "target_component": "unknown",
            "boundary_direction": "scheduler->unknown",
        }
    )

    assert result["ok"] is False
    assert result["schema"] == RUNTIME_BOUNDARY_SCHEMA
    assert result["reason"] == "runtime_boundary_unknown_components"
    assert result["invalid_fields"] == ["target_component"]
