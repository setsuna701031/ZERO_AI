from pathlib import Path

from core.runtime import aer_runtime_recovery_canonical_request as canonical_request
from core.runtime.aer_runtime_recovery_canonical_request import (
    RECOVERY_CANONICAL_REQUEST_DENIED_CAPABILITIES,
    RECOVERY_CANONICAL_REQUEST_SCHEMA,
    prepare_canonical_runtime_recovery_request,
)


def test_strict_all_exports_only_request_api() -> None:
    assert canonical_request.__all__ == [
        "prepare_canonical_runtime_recovery_request",
    ]
    assert set(canonical_request.__all__) == {"prepare_canonical_runtime_recovery_request"}


def test_canonical_request_returns_disabled_plain_dict() -> None:
    request = prepare_canonical_runtime_recovery_request(
        request_id="request-1",
        surface_id="surface-1",
        runtime_identity={"runtime": "main", "tags": ("disabled",)},
        recovery_reason="operator_requested_observation",
        recovery_mode="observe",
        recovery_context={"attempt": 1, "nested": {"tuple": ("a", "b")}},
    )

    assert request["schema"] == RECOVERY_CANONICAL_REQUEST_SCHEMA
    assert request["request_id"] == "request-1"
    assert request["surface_id"] == "surface-1"
    assert request["runtime_identity"] == {"runtime": "main", "tags": ["disabled"]}
    assert request["recovery_reason"] == "operator_requested_observation"
    assert request["recovery_mode"] == "observe"
    assert request["recovery_context"] == {"attempt": 1, "nested": {"tuple": ["a", "b"]}}
    assert request["prepared"] is True
    assert request["blocked"] is False
    assert request["denied"] is False
    assert request["status"] == "prepared"
    assert request["disabled"] is True
    assert request["execution_allowed"] is False
    assert request["recovery_enabled"] is False
    assert request["runtime_state_mutated"] is False
    assert request["surface_wired"] is False
    assert request["owned_by_canonical_surface_family"] is True
    assert request["request_helper_connected_to_surface_helper"] is False
    assert request["surface_connection_requires_future_go_review"] is True
    assert request["canonical_surface_called"] is False
    assert request["public_compatibility_boundary"] is True
    assert request["append_only_public_schema"] is True
    assert request["existing_public_fields_renamable"] is False
    assert request["existing_public_fields_removable"] is False
    assert request["future_fields_must_be_optional"] is True
    assert request["major_version_required_for_breaking_schema_change"] is True
    assert request["exactly_one_canonical_request_schema"] is True
    assert request["competing_public_request_formats_allowed"] is False
    assert request["future_implementations_must_consume_this_request"] is True
    assert request["intent_only"] is True
    assert request["execution_request"] is False
    assert request["runtime_caller_modified"] is False
    assert request["runtime_supervisor_bridge_changed"] is False
    assert request["hooks_registered"] is False
    assert request["binding_applied"] is False
    assert request["endpoint_invoked"] is False
    assert request["scheduler_called"] is False
    assert request["taskrunner_called"] is False
    assert request["operator_called"] is False
    assert request["dispatcher_called"] is False
    assert request["supervisor_called"] is False
    assert request["native_runtime_called"] is False
    assert request["watchdog_called"] is False
    assert request["persistence_called"] is False
    assert request["audit_called"] is False
    assert request["journal_called"] is False
    assert request["subprocess_called"] is False
    assert request["filesystem_mutation_called"] is False
    assert request["compatible_with_canonical_surface"] is True
    assert request["does_not_replace_canonical_surface"] is True
    assert request["does_not_bypass_canonical_surface"] is True
    assert request["plain_dict_only"] is True


def test_canonical_request_denies_runtime_attempts_as_data_only() -> None:
    request = prepare_canonical_runtime_recovery_request(
        request_id="request-denied",
        surface_id="surface-1",
        recovery_reason="attempted_execution",
        request_execution=True,
        request_enablement=True,
        request_surface_call=True,
        request_hook_registration=True,
        request_binding_application=True,
        request_endpoint_invocation=True,
        request_runtime_mutation=True,
    )

    assert request["prepared"] is False
    assert request["blocked"] is False
    assert request["denied"] is True
    assert request["status"] == "denied"
    assert "denied" in str(request["reason"])
    assert request["canonical_surface_called"] is False
    assert request["execution_allowed"] is False
    assert request["runtime_state_mutated"] is False
    assert request["denied_capabilities"] == list(RECOVERY_CANONICAL_REQUEST_DENIED_CAPABILITIES)


def test_canonical_request_blocks_unknown_mode_without_side_effects() -> None:
    request = prepare_canonical_runtime_recovery_request(
        request_id="request-blocked",
        surface_id="surface-1",
        recovery_reason="unknown_mode",
        recovery_mode="execute_now",
    )

    assert request["prepared"] is False
    assert request["blocked"] is True
    assert request["denied"] is False
    assert request["status"] == "blocked"
    assert request["execution_allowed"] is False
    assert "unsupported" in str(request["reason"])


def test_canonical_request_module_has_no_runtime_or_execution_imports() -> None:
    text = Path("core/runtime/aer_runtime_recovery_canonical_request.py").read_text(encoding="utf-8")
    import_lines = [line for line in text.splitlines() if line.startswith("import ") or line.startswith("from ")]
    forbidden = [
        "aer_runtime_recovery_canonical_surface",
        "runtime_supervisor_bridge",
        "scheduler",
        "taskrunner",
        "operator",
        "dispatcher",
        "supervisor",
        "native_runtime",
        "watchdog",
        "subprocess",
        "Path(",
    ]

    for phrase in forbidden:
        assert all(phrase not in line for line in import_lines)


def test_public_schema_is_append_only_and_unique() -> None:
    request = prepare_canonical_runtime_recovery_request(
        request_id="request-compat",
        surface_id="surface-1",
        recovery_reason="compatibility_check",
    )

    assert request["schema"] == RECOVERY_CANONICAL_REQUEST_SCHEMA
    assert request["append_only_public_schema"] is True
    assert request["exactly_one_canonical_request_schema"] is True
    assert request["competing_public_request_formats_allowed"] is False
    assert request["intent_only"] is True
    assert request["execution_request"] is False
    public_entry_apis = [name for name in canonical_request.__all__ if name.startswith("prepare_")]
    assert public_entry_apis == ["prepare_canonical_runtime_recovery_request"]


def test_no_additional_public_prepare_request_functions() -> None:
    public_prepare_functions = [
        name
        for name, value in vars(canonical_request).items()
        if name.startswith("prepare_")
        and "runtime_recovery" in name
        and callable(value)
        and not name.startswith("_")
    ]

    assert public_prepare_functions == ["prepare_canonical_runtime_recovery_request"]
    forbidden_public_names = [
        "build_canonical_runtime_recovery_request",
        "create_canonical_runtime_recovery_request",
        "prepare_runtime_recovery_request",
        "prepare_legacy_runtime_recovery_request",
        "canonical_runtime_recovery_request",
    ]
    for name in forbidden_public_names:
        assert name not in canonical_request.__all__
        assert not hasattr(canonical_request, name)


def test_existing_runtime_modules_do_not_import_or_call_canonical_request() -> None:
    runtime_root = Path("core/runtime")
    forbidden = [
        "aer_runtime_recovery_canonical_request",
        "prepare_canonical_runtime_recovery_request",
    ]

    for path in runtime_root.glob("*.py"):
        if path.name == "aer_runtime_recovery_canonical_request.py":
            continue
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text, f"{path} must not import or call Package 243 request helper"
