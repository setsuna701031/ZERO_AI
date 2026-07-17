from pathlib import Path

from core.runtime import aer_runtime_recovery_canonical_response as canonical_response
from core.runtime.aer_runtime_recovery_canonical_response import (
    prepare_canonical_runtime_recovery_response,
)


def test_strict_all_exports_only_response_api() -> None:
    assert canonical_response.__all__ == [
        "prepare_canonical_runtime_recovery_response",
    ]
    public_entry_apis = [name for name in canonical_response.__all__ if name.startswith("prepare_")]
    assert public_entry_apis == ["prepare_canonical_runtime_recovery_response"]


def test_canonical_response_returns_observation_only_plain_dict() -> None:
    response = prepare_canonical_runtime_recovery_response(
        response_id="response-1",
        request_id="request-1",
        surface_id="surface-1",
        runtime_identity={"runtime": "main", "tags": ("disabled",)},
        accepted=True,
        status="observed",
        reason="request_observed",
        diagnostics={"tuple": ("a", "b")},
        timestamp="2026-07-02T00:00:00Z",
    )

    assert response["schema"] == "aer.runtime.recovery.canonical_response.v1"
    assert response["response_id"] == "response-1"
    assert response["request_id"] == "request-1"
    assert response["surface_id"] == "surface-1"
    assert response["runtime_identity"] == {"runtime": "main", "tags": ["disabled"]}
    assert response["accepted"] is True
    assert response["execution_allowed"] is False
    assert response["recovery_enabled"] is False
    assert response["status"] == "observed"
    assert response["reason"] == "request_observed"
    assert response["diagnostics"] == {"tuple": ["a", "b"]}
    assert response["timestamp"] == "2026-07-02T00:00:00Z"
    assert response["observation_only"] is True
    assert response["runtime_state_mutated"] is False
    assert response["filesystem_mutation_called"] is False
    assert response["subprocess_called"] is False
    assert response["audit_called"] is False
    assert response["journal_called"] is False
    assert response["persistence_called"] is False
    assert response["scheduler_called"] is False
    assert response["taskrunner_called"] is False
    assert response["operator_called"] is False
    assert response["dispatcher_called"] is False
    assert response["supervisor_called"] is False
    assert response["native_runtime_called"] is False
    assert response["watchdog_called"] is False
    assert response["binding_endpoint_called"] is False
    assert response["activation_gate_called"] is False
    assert response["canonical_surface_called"] is False
    assert response["request_helper_called"] is False
    assert response["executes_recovery"] is False
    assert response["authorizes_recovery"] is False
    assert response["schedules_recovery"] is False
    assert response["dispatches_recovery"] is False
    assert response["recovers"] is False
    assert response["plain_dict_only"] is True


def test_canonical_response_denies_runtime_attempts_as_data_only() -> None:
    response = prepare_canonical_runtime_recovery_response(
        response_id="response-denied",
        request_id="request-1",
        surface_id="surface-1",
        request_execution=True,
        request_authorization=True,
        request_schedule=True,
        request_dispatch=True,
        request_mutation=True,
        request_recovery=True,
        request_runtime_invocation=True,
        request_surface_call=True,
        request_request_helper_call=True,
        request_binding_endpoint_call=True,
        request_activation_gate_call=True,
    )

    assert response["accepted"] is False
    assert response["prepared"] is False
    assert response["denied"] is True
    assert response["status"] == "denied"
    assert "denied" in str(response["reason"])
    assert response["execution_allowed"] is False
    assert response["recovery_enabled"] is False
    assert response["runtime_state_mutated"] is False
    assert response["canonical_surface_called"] is False
    assert response["request_helper_called"] is False
    assert response["binding_endpoint_called"] is False
    assert response["activation_gate_called"] is False


def test_canonical_response_compatibility_boundary() -> None:
    response = prepare_canonical_runtime_recovery_response(
        response_id="response-compat",
        request_id="request-1",
        surface_id="surface-1",
    )

    assert response["append_only_public_schema"] is True
    assert response["backward_compatible"] is True
    assert response["exactly_one_public_response_api"] is True
    assert response["public_response_api"] == "prepare_canonical_runtime_recovery_response"
    assert response["exactly_one_canonical_response_schema"] is True
    assert response["competing_public_response_formats_allowed"] is False
    assert response["only_public_runtime_recovery_response_object"] is True
    assert response["future_packages_must_return_this_shape"] is True
    assert response["only_surface_may_publicly_return_response"] is True
    assert response["future_implementations_return_through_canonical_surface"] is True
    assert response["public_direct_response_exposure_allowed"] is False
    assert response["additional_public_response_apis_allowed"] is False
    assert response["response_helper_internal_compatibility_artifact"] is True
    assert response["standalone_runtime_entry_point"] is False
    assert response["response_helper_public_runtime_entry_point"] is False
    assert response["canonical_surface_bypass_allowed"] is False
    assert response["surface_owns_public_runtime_recovery_entry"] is True
    assert response["surface_owns_request_admission"] is True
    assert response["surface_owns_request_normalization"] is True
    assert response["surface_owns_response_return"] is True
    assert response["surface_owns_recovery_execution"] is False
    assert response["surface_owns_recovery_planning"] is False
    assert response["surface_owns_recovery_scheduling"] is False
    assert response["surface_owns_recovery_supervision"] is False
    assert response["surface_owns_recovery_state_machine"] is False
    assert response["surface_owns_recovery_persistence"] is False
    assert response["surface_owns_recovery_audit"] is False
    assert response["surface_owns_recovery_journal"] is False
    assert response["owns_response_normalization"] is True
    assert response["owns_response_validation"] is True
    assert response["owns_response_compatibility"] is True
    assert response["owns_execution"] is False
    assert response["owns_planning"] is False
    assert response["owns_scheduling"] is False
    assert response["owns_recovery_policy"] is False
    assert response["owns_recovery_state"] is False
    assert response["owns_runtime_mutation"] is False
    assert response["owns_dispatcher"] is False
    assert response["owns_operator"] is False
    assert response["owns_supervisor"] is False
    assert response["owns_watchdog"] is False
    assert response["owns_persistence"] is False
    assert response["owns_audit"] is False
    assert response["owns_journal"] is False


def test_response_module_has_no_runtime_execution_imports_or_extra_apis() -> None:
    text = Path("core/runtime/aer_runtime_recovery_canonical_response.py").read_text(encoding="utf-8")
    import_lines = [line for line in text.splitlines() if line.startswith("import ") or line.startswith("from ")]
    forbidden_imports = [
        "aer_runtime_recovery_canonical_request",
        "aer_runtime_recovery_canonical_surface",
        "binding_endpoint",
        "activation_gate",
        "scheduler",
        "taskrunner",
        "operator",
        "dispatcher",
        "supervisor",
        "native_runtime",
        "watchdog",
        "subprocess",
        "Path",
    ]

    for phrase in forbidden_imports:
        assert all(phrase not in line for line in import_lines)

    public_prepare_functions = [
        name
        for name, value in vars(canonical_response).items()
        if name.startswith("prepare_")
        and "runtime_recovery" in name
        and callable(value)
        and not name.startswith("_")
    ]
    assert public_prepare_functions == ["prepare_canonical_runtime_recovery_response"]
    assert canonical_response.__all__ == ["prepare_canonical_runtime_recovery_response"]
    forbidden_public_names = [
        "build_canonical_runtime_recovery_response",
        "create_canonical_runtime_recovery_response",
        "prepare_runtime_recovery_response",
        "prepare_legacy_runtime_recovery_response",
        "canonical_runtime_recovery_response",
    ]
    for name in forbidden_public_names:
        assert name not in canonical_response.__all__
        assert not hasattr(canonical_response, name)


def _canonical_response_callers(paths: list[Path]) -> list[Path]:
    forbidden = [
        "aer_runtime_recovery_canonical_response",
        "prepare_canonical_runtime_recovery_response",
    ]
    allowed = {
        "aer_runtime_recovery_canonical_response.py",
        "aer_runtime_recovery_surface_integration.py",
    }
    callers = []
    for path in paths:
        if path.name in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        if any(phrase in text for phrase in forbidden):
            callers.append(path)
    return callers


def test_only_package_251_integration_may_call_canonical_response() -> None:
    assert _canonical_response_callers(list(Path("core/runtime").glob("*.py"))) == []


def test_second_runtime_canonical_response_caller_is_rejected(tmp_path: Path) -> None:
    second = tmp_path / "second_runtime_caller.py"
    second.write_text("from core.runtime.aer_runtime_recovery_canonical_response import prepare_canonical_runtime_recovery_response\n", encoding="utf-8")
    assert _canonical_response_callers([second]) == [second]
