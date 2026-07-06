from __future__ import annotations

from types import MappingProxyType

import pytest

from core.runtime.runtime_controlled_read_execution import (
    build_runtime_controlled_read_audit_record,
    build_runtime_controlled_read_execution_request,
    build_runtime_controlled_read_milestone_seal,
    execute_runtime_controlled_read,
    validate_runtime_controlled_read_execution_request,
)


def _session_id():
    return "limited-runtime-session::birth-1209"


def _lease():
    return {
        "lease_id": "execution-lease::limited-runtime-session::birth-1209::lease-1217",
        "runtime_session_id": _session_id(),
        "lease_status": "granted",
    }


def _grant():
    return {
        "capability_grant_id": (
            "capability-grant::limited-runtime-session::birth-1209::"
            "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
            "capability-1225"
        ),
        "owner_session_id": _session_id(),
        "owner_lease_id": _lease()["lease_id"],
        "grant_status": "granted",
    }


def _binding():
    return {
        "executor_binding_id": "executor-binding::executor-zero::binding-1233",
        "runtime_session_id": _session_id(),
        "execution_lease_id": _lease()["lease_id"],
        "capability_grant_id": _grant()["capability_grant_id"],
        "binding_status": "bound",
    }


def _boundary():
    return {
        "tool_boundary_id": "tool-boundary::read::inspect_state::tool-boundary-1241",
        "runtime_session_id": _session_id(),
        "execution_lease_id": _lease()["lease_id"],
        "capability_grant_id": _grant()["capability_grant_id"],
        "executor_binding_id": _binding()["executor_binding_id"],
        "tool_boundary_status": "admitted",
        "admission_granted": True,
    }


def _invocation():
    return {
        "tool_invocation_id": "tool-invocation::inspect_state::tool-invocation-1249",
        "runtime_session_id": _session_id(),
        "execution_lease_id": _lease()["lease_id"],
        "capability_grant_id": _grant()["capability_grant_id"],
        "executor_binding_id": _binding()["executor_binding_id"],
        "tool_boundary_id": _boundary()["tool_boundary_id"],
        "invocation_status": "approved",
    }


def _adapter(resource="README.md"):
    return {
        "read_adapter_id": "read-adapter::README.md::read-adapter-1257",
        "runtime_session_id": _session_id(),
        "execution_lease_id": _lease()["lease_id"],
        "capability_grant_id": _grant()["capability_grant_id"],
        "executor_binding_id": _binding()["executor_binding_id"],
        "tool_boundary_id": _boundary()["tool_boundary_id"],
        "tool_invocation_id": _invocation()["tool_invocation_id"],
        "requested_resource": resource,
        "read_status": "planned",
        "resource_ownership": {
            "owner_session_id": _session_id(),
            "ownership_verified": True,
        },
        "read_scope_model": {
            "resource_in_scope": True,
            "controlled_read_allowed": True,
        },
    }


def _request(**overrides):
    request = build_runtime_controlled_read_execution_request(
        read_execution_request_id="read-execution-1265",
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_binding=_binding(),
        tool_boundary=_boundary(),
        tool_invocation=_invocation(),
        read_adapter=_adapter(),
        workspace_root="E:\\zero_ai",
    )
    request.update(overrides)
    return request


def test_1265_no_adapter_blocks_read():
    validation = validate_runtime_controlled_read_execution_request(
        _request(read_adapter={})
    )

    assert validation["read_allowed"] is False
    assert "missing_read_adapter" in validation["problems"]


def test_1266_invalid_session_blocks_read():
    validation = validate_runtime_controlled_read_execution_request(
        _request(runtime_session_id=None)
    )

    assert validation["read_allowed"] is False
    assert "invalid_runtime_session_id" in validation["problems"]


def test_1267_invalid_lease_blocks_read():
    validation = validate_runtime_controlled_read_execution_request(
        _request(execution_lease={**_lease(), "lease_status": "expired"})
    )

    assert validation["read_allowed"] is False
    assert "inactive_execution_lease" in validation["problems"]


def test_1268_invalid_capability_blocks_read():
    validation = validate_runtime_controlled_read_execution_request(
        _request(capability_grant={**_grant(), "grant_status": "revoked"})
    )

    assert validation["read_allowed"] is False
    assert "inactive_capability_grant" in validation["problems"]


def test_1268_invalid_executor_blocks_read():
    validation = validate_runtime_controlled_read_execution_request(
        _request(executor_binding={**_binding(), "binding_status": "revoked"})
    )

    assert validation["read_allowed"] is False
    assert "inactive_executor_binding" in validation["problems"]


def test_1269_invalid_boundary_blocks_read():
    validation = validate_runtime_controlled_read_execution_request(
        _request(tool_boundary={**_boundary(), "tool_boundary_status": "denied"})
    )

    assert validation["read_allowed"] is False
    assert "inactive_tool_boundary" in validation["problems"]


def test_1269_invalid_invocation_blocks_read():
    validation = validate_runtime_controlled_read_execution_request(
        _request(tool_invocation={**_invocation(), "invocation_status": "revoked"})
    )

    assert validation["read_allowed"] is False
    assert "inactive_tool_invocation" in validation["problems"]


def test_1270_revoked_adapter_blocks_read():
    validation = validate_runtime_controlled_read_execution_request(
        _request(read_adapter={**_adapter(), "read_status": "revoked"})
    )

    assert validation["read_allowed"] is False
    assert "inactive_read_adapter" in validation["problems"]


def test_1270_approved_adapter_allows_controlled_read():
    execution = execute_runtime_controlled_read(_request())

    assert execution["execution_status"] == "succeeded"
    assert execution["read_adapter_id"] == _adapter()["read_adapter_id"]
    assert execution["requested_resource"] == "README.md"
    assert execution["content_digest"]
    assert execution["content_metadata"]["content_length"] > 0
    assert execution["content_metadata"]["content_included"] is False


def test_1271_read_creates_immutable_evidence():
    execution = execute_runtime_controlled_read(_request())

    assert isinstance(execution, MappingProxyType)
    assert execution["immutable_record"] is True
    assert execution["read_replay_record"]["immutable"] is True
    assert execution["read_replay_record"]["content_digest"] == execution["content_digest"]
    with pytest.raises(TypeError):
        execution["execution_status"] = "mutated"


def test_1271_read_cannot_write():
    execution = execute_runtime_controlled_read(_request())

    assert execution["file_write_performed"] is False
    assert execution["append_performed"] is False
    assert execution["delete_performed"] is False
    assert execution["rename_performed"] is False
    assert execution["chmod_performed"] is False


def test_1272_read_cannot_mutate():
    execution = execute_runtime_controlled_read(_request())

    assert execution["mutation_performed"] is False
    assert execution["network_performed"] is False
    assert execution["task_executed"] is False
    assert execution["autonomy_started"] is False
    assert execution["background_loop_started"] is False


def test_1272_read_cannot_execute_command_and_audit_seal():
    execution = execute_runtime_controlled_read(_request())
    audit = build_runtime_controlled_read_audit_record(_request())
    seal = build_runtime_controlled_read_milestone_seal(_request())

    assert execution["subprocess_started"] is False
    assert execution["shell_started"] is False
    assert audit["decision"] == "reserved_runtime_controlled_read_execution_only"
    assert audit["read_allowed"] is True
    assert audit["file_write_performed"] is False
    assert audit["mutation_performed"] is False
    assert audit["subprocess_started"] is False
    assert audit["shell_started"] is False
    assert seal["closed"] is True
    assert seal["next_package"] == 1273
    assert seal["all_modification_surfaces_locked"] is True
