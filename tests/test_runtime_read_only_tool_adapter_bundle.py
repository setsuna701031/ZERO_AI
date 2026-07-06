from __future__ import annotations

from core.runtime.runtime_read_only_tool_adapter import (
    READ_ADAPTER_STATUSES,
    build_runtime_read_only_tool_adapter_audit_record,
    build_runtime_read_only_tool_adapter_audit_projection,
    build_runtime_read_only_tool_adapter_milestone_seal,
    build_runtime_read_only_tool_adapter_request,
    expire_runtime_read_only_tool_adapter,
    revoke_runtime_read_only_tool_adapter,
    validate_runtime_read_only_tool_adapter_request,
)


def _session_id():
    return "limited-runtime-session::birth-1209"


def _lease():
    return {
        "lease_id": "execution-lease::limited-runtime-session::birth-1209::lease-1217",
        "runtime_session_id": _session_id(),
        "lease_status": "granted",
    }


def _grant(read_access=True):
    return {
        "capability_grant_id": (
            "capability-grant::limited-runtime-session::birth-1209::"
            "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
            "capability-1225"
        ),
        "owner_session_id": _session_id(),
        "owner_lease_id": _lease()["lease_id"],
        "grant_status": "granted",
        "granted_capabilities": {
            "read_access": read_access,
            "write_access": False,
            "tool_access": False,
            "execution_access": False,
            "mutation_access": False,
            "network_access": False,
        },
    }


def _binding():
    return {
        "executor_binding_id": (
            "executor-binding::limited-runtime-session::birth-1209::"
            "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
            "capability-grant::limited-runtime-session::birth-1209::"
            "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
            "capability-1225::executor-zero::binding-1233"
        ),
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
        "requested_tool_name": "inspect_state",
        "requested_tool_type": "read_tool",
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
        "tool_name": "inspect_state",
        "invocation_status": "approved",
        "actual_tool_executed": False,
        "filesystem_access_allowed": False,
    }


def _authorized_request(**overrides):
    request = build_runtime_read_only_tool_adapter_request(
        read_adapter_request_id="read-adapter-1257",
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_binding=_binding(),
        tool_boundary=_boundary(),
        tool_invocation=_invocation(),
        requested_resource="workspace://docs/example.md",
        resource_ownership={
            "owner_session_id": _session_id(),
            "ownership_verified": True,
        },
        read_scope_model={
            "scope_type": "dry_run_resource_reference",
            "resource_in_scope": True,
            "filesystem_resolution_allowed": False,
        },
    )
    request.update(overrides)
    return request


def test_1257_no_invocation_no_read_adapter():
    request = _authorized_request(tool_invocation={})

    validation = validate_runtime_read_only_tool_adapter_request(request)

    assert validation["read_adapter_created"] is False
    assert validation["read_adapter_record"] is None
    assert "missing_tool_invocation" in validation["problems"]


def test_1258_invalid_session_blocks_adapter():
    validation = validate_runtime_read_only_tool_adapter_request(
        _authorized_request(runtime_session_id=None)
    )

    assert validation["read_adapter_created"] is False
    assert "invalid_runtime_session_id" in validation["problems"]


def test_1259_invalid_lease_blocks_adapter():
    validation = validate_runtime_read_only_tool_adapter_request(
        _authorized_request(execution_lease={**_lease(), "lease_status": "expired"})
    )

    assert validation["read_adapter_created"] is False
    assert "inactive_execution_lease" in validation["problems"]


def test_1260_invalid_capability_blocks_adapter():
    validation = validate_runtime_read_only_tool_adapter_request(
        _authorized_request(capability_grant={**_grant(), "grant_status": "revoked"})
    )

    assert validation["read_adapter_created"] is False
    assert "inactive_capability_grant" in validation["problems"]


def test_1260_invalid_executor_blocks_adapter():
    validation = validate_runtime_read_only_tool_adapter_request(
        _authorized_request(executor_binding={**_binding(), "binding_status": "expired"})
    )

    assert validation["read_adapter_created"] is False
    assert "inactive_executor_binding" in validation["problems"]


def test_1261_invalid_tool_boundary_blocks_adapter():
    validation = validate_runtime_read_only_tool_adapter_request(
        _authorized_request(
            tool_boundary={**_boundary(), "tool_boundary_status": "denied"}
        )
    )

    assert validation["read_adapter_created"] is False
    assert "inactive_tool_boundary" in validation["problems"]


def test_1261_invalid_invocation_blocks_adapter():
    validation = validate_runtime_read_only_tool_adapter_request(
        _authorized_request(
            tool_invocation={**_invocation(), "invocation_status": "revoked"}
        )
    )

    assert validation["read_adapter_created"] is False
    assert "inactive_tool_invocation" in validation["problems"]


def test_1262_missing_read_permission_blocks_adapter():
    validation = validate_runtime_read_only_tool_adapter_request(
        _authorized_request(capability_grant=_grant(read_access=False))
    )

    assert validation["read_adapter_created"] is False
    assert "read_capability_missing" in validation["problems"]


def test_1263_authorized_request_creates_read_plan_record_only():
    validation = validate_runtime_read_only_tool_adapter_request(_authorized_request())
    adapter = validation["read_adapter_record"]

    assert validation["read_adapter_created"] is True
    assert adapter["read_adapter_id"].startswith("read-adapter::")
    assert adapter["requested_resource"] == "workspace://docs/example.md"
    assert adapter["read_status"] == "planned"
    assert adapter["read_result"]["result_type"] == "synthetic_read_plan_only"
    assert adapter["read_result"]["content"] is None
    assert adapter["read_result"]["filesystem_touched"] is False
    assert adapter["denial_reason"] == "none"
    assert adapter["supported_statuses"] == list(READ_ADAPTER_STATUSES)


def test_1263_adapter_does_not_open_files():
    adapter = validate_runtime_read_only_tool_adapter_request(_authorized_request())[
        "read_adapter_record"
    ]

    assert adapter["file_open_performed"] is False
    assert adapter["pathlib_read_performed"] is False


def test_1264_adapter_does_not_read_filesystem():
    adapter = validate_runtime_read_only_tool_adapter_request(_authorized_request())[
        "read_adapter_record"
    ]
    projection = build_runtime_read_only_tool_adapter_audit_projection(adapter)

    assert adapter["filesystem_access_performed"] is False
    assert projection["filesystem_access_performed"] is False
    assert adapter["read_scope_model"]["filesystem_resolution_allowed"] is False


def test_1264_adapter_cannot_write():
    adapter = validate_runtime_read_only_tool_adapter_request(_authorized_request())[
        "read_adapter_record"
    ]

    assert adapter["write_performed"] is False
    assert adapter["network_performed"] is False
    assert adapter["subprocess_started"] is False
    assert adapter["shell_started"] is False


def test_1264_adapter_cannot_mutate_and_audit_seal_are_data_only():
    adapter = validate_runtime_read_only_tool_adapter_request(_authorized_request())[
        "read_adapter_record"
    ]
    expired = expire_runtime_read_only_tool_adapter(adapter, current_tick=1)
    revoked = revoke_runtime_read_only_tool_adapter(adapter, reason="operator_revoked")
    audit = build_runtime_read_only_tool_adapter_audit_record(_authorized_request())
    seal = build_runtime_read_only_tool_adapter_milestone_seal(_authorized_request())

    assert adapter["mutation_performed"] is False
    assert adapter["task_executed"] is False
    assert adapter["autonomy_started"] is False
    assert adapter["background_loop_started"] is False
    assert expired["read_status"] == "expired"
    assert expired["filesystem_access_performed"] is False
    assert revoked["read_status"] == "revoked"
    assert revoked["filesystem_access_performed"] is False
    assert audit["decision"] == "reserved_runtime_read_only_tool_adapter_plan_record_only"
    assert audit["read_adapter_created"] is True
    assert audit["file_open_performed"] is False
    assert audit["filesystem_access_performed"] is False
    assert audit["write_performed"] is False
    assert audit["mutation_performed"] is False
    assert seal["closed"] is True
    assert seal["next_package"] == 1265
    assert seal["all_filesystem_surfaces_locked"] is True
