from pathlib import Path

from core.runtime import aer_runtime_recovery_canonical_surface as canonical
from core.runtime.aer_runtime_recovery_canonical_surface import (
    RECOVERY_CANONICAL_SURFACE_CONTRACT,
    RECOVERY_CANONICAL_SURFACE_DENIED_CAPABILITIES,
    RECOVERY_CANONICAL_SURFACE_NAME,
    prepare_canonical_runtime_recovery_surface,
)


def test_strict_all_exports_only_canonical_surface_api() -> None:
    assert canonical.__all__ == [
        "RECOVERY_CANONICAL_SURFACE_CONTRACT",
        "RECOVERY_CANONICAL_SURFACE_NAME",
        "RECOVERY_CANONICAL_SURFACE_ALLOWED_STATUSES",
        "RECOVERY_CANONICAL_SURFACE_DENIED_CAPABILITIES",
        "prepare_canonical_runtime_recovery_surface",
    ]
    public_entry_apis = [name for name in canonical.__all__ if name.startswith("prepare_")]
    assert public_entry_apis == ["prepare_canonical_runtime_recovery_surface"]


def test_canonical_surface_report_is_prepared_but_disabled() -> None:
    report = prepare_canonical_runtime_recovery_surface(
        surface_id="surface-1",
        metadata={"tuple": ("a", "b")},
    )

    assert report["contract"] == RECOVERY_CANONICAL_SURFACE_CONTRACT
    assert report["surface_id"] == "surface-1"
    assert report["surface_name"] == RECOVERY_CANONICAL_SURFACE_NAME
    assert report["prepared"] is True
    assert report["blocked"] is False
    assert report["denied"] is False
    assert report["status"] == "prepared"
    assert report["canonical_surface"] is True
    assert report["single_canonical_surface"] is True
    assert report["only_public_runtime_recovery_entry_surface"] is True
    assert report["public_entry_api"] == "prepare_canonical_runtime_recovery_surface"
    assert report["competing_public_runtime_recovery_surfaces"] == []
    assert report["competing_entry_points_allowed"] is False
    assert report["future_recovery_entry_must_flow_through_surface"] is True
    assert report["future_packages_must_enter_through_surface"] is True
    assert report["future_public_entry_api_allowed"] is False
    assert report["future_connectors_require_go_review"] is True
    assert report["owns_public_runtime_recovery_interface_only"] is True
    assert report["owns_recovery_policy"] is False
    assert report["owns_recovery_planning"] is False
    assert report["owns_recovery_scheduling"] is False
    assert report["owns_recovery_execution"] is False
    assert report["owns_recovery_supervision"] is False
    assert report["owns_recovery_state_machine"] is False
    assert report["owns_recovery_persistence"] is False
    assert report["owns_recovery_audit"] is False
    assert report["owns_recovery_journaling"] is False
    assert report["owns_recovery_hook_registration"] is False
    assert report["owns_recovery_binding"] is False
    assert report["owns_recovery_endpoint_invocation"] is False
    assert report["may_validate_normalize_forward_after_go"] is True
    assert report["stable_compatibility_boundary"] is True
    assert report["public_api_stable"] is True
    assert report["ownership_boundary_stable"] is True
    assert report["requires_major_version_for_breaking_public_api"] is True
    assert report["silent_replacement_allowed"] is False
    assert report["bypass_allowed"] is False
    assert report["silent_deprecation_allowed"] is False
    assert report["all_callers_must_remain_compatible"] is True
    assert report["surface_enabled"] is False
    assert report["surface_wired_into_runtime"] is False
    assert report["runtime_wiring_enabled"] is False
    assert report["runtime_supervisor_bridge_changed"] is False
    assert report["runtime_hook_registered"] is False
    assert report["runtime_binding_applied"] is False
    assert report["endpoint_invoked"] is False
    assert report["event_emitted"] is False
    assert report["recovery_enabled"] is False
    assert report["activation_allowed"] is False
    assert report["execution_allowed"] is False
    assert report["scheduler_called"] is False
    assert report["taskrunner_called"] is False
    assert report["operator_called"] is False
    assert report["dispatcher_called"] is False
    assert report["supervisor_called"] is False
    assert report["native_runtime_called"] is False
    assert report["watchdog_called"] is False
    assert report["runtime_state_mutated"] is False
    assert report["persistence_called"] is False
    assert report["audit_called"] is False
    assert report["journal_called"] is False
    assert report["subprocess_called"] is False
    assert report["filesystem_mutation_called"] is False
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["plain_dict_only"] is True
    assert report["metadata"] == {"tuple": ["a", "b"]}


def test_canonical_surface_denies_activation_and_execution_attempts_as_data_only() -> None:
    report = prepare_canonical_runtime_recovery_surface(
        request_activation=True,
        request_execution=True,
        request_hook_registration=True,
        request_binding_application=True,
        request_endpoint_invocation=True,
        request_event_emission=True,
        request_runtime_mutation=True,
        request_persistence=True,
        request_audit=True,
        request_journal=True,
        request_subprocess=True,
        request_filesystem_mutation=True,
    )

    assert report["prepared"] is False
    assert report["blocked"] is False
    assert report["denied"] is True
    assert report["status"] == "denied"
    assert "denied" in str(report["reason"])
    assert report["surface_enabled"] is False
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["denied_capabilities"] == list(RECOVERY_CANONICAL_SURFACE_DENIED_CAPABILITIES)


def test_canonical_surface_blocks_competing_surface_name() -> None:
    report = prepare_canonical_runtime_recovery_surface(requested_surface="runtime_recovery_other_surface")

    assert report["prepared"] is False
    assert report["blocked"] is True
    assert report["denied"] is False
    assert report["surface_name"] is None
    assert RECOVERY_CANONICAL_SURFACE_NAME in str(report["reason"])


def _canonical_surface_callers(paths: list[Path]) -> list[Path]:
    forbidden = [
        "aer_runtime_recovery_canonical_surface",
        "prepare_canonical_runtime_recovery_surface",
    ]
    allowed = {
        "aer_runtime_recovery_canonical_surface.py",
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


def test_only_package_251_integration_may_call_canonical_surface() -> None:
    assert _canonical_surface_callers(list(Path("core/runtime").glob("*.py"))) == []


def test_second_runtime_canonical_surface_caller_is_rejected(tmp_path: Path) -> None:
    second = tmp_path / "second_runtime_caller.py"
    second.write_text("from core.runtime.aer_runtime_recovery_canonical_surface import prepare_canonical_runtime_recovery_surface\n", encoding="utf-8")
    assert _canonical_surface_callers([second]) == [second]


def test_exactly_one_public_canonical_surface_module_and_no_competing_public_surface() -> None:
    canonical_modules = list(Path("core/runtime").glob("aer_runtime_recovery_canonical_surface.py"))
    assert [path.name for path in canonical_modules] == ["aer_runtime_recovery_canonical_surface.py"]

    report = prepare_canonical_runtime_recovery_surface()
    assert report["only_public_runtime_recovery_entry_surface"] is True
    assert report["public_entry_api"] == "prepare_canonical_runtime_recovery_surface"
    assert report["competing_public_runtime_recovery_surfaces"] == []
