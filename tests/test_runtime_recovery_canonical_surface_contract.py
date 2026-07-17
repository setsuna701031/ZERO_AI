from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/canonical_runtime_recovery_surface_v1.md")


def test_canonical_surface_contract_exists_and_names_single_surface() -> None:
    text = CONTRACT.read_text(encoding="utf-8")

    assert "aer.runtime.recovery.canonical_surface.v1" in text
    assert "runtime_recovery_canonical_surface" in text
    assert "exactly one canonical Runtime Recovery surface" in text
    assert "must not create multiple Runtime Recovery entry points" in text
    assert "single canonical surface" in text
    assert "must not introduce competing Runtime entry paths" in text
    assert "ONLY public Runtime Recovery entry surface" in text
    assert "No future package may expose another public Runtime Recovery entry API" in text
    assert "may only connect to this canonical surface in future packages after the required GO reviews" in text


def test_canonical_surface_contract_pins_disabled_safety_fields() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    required = [
        "surface_enabled: false",
        "only_public_runtime_recovery_entry_surface: true",
        "public_entry_api: prepare_canonical_runtime_recovery_surface",
        "competing_public_runtime_recovery_surfaces: []",
        "runtime_wiring_enabled: false",
        "runtime_hook_registered: false",
        "runtime_binding_applied: false",
        "endpoint_invoked: false",
        "event_emitted: false",
        "recovery_enabled: false",
        "executes_recovery: false",
        "runtime_state_mutated: false",
        "side_effects_performed: false",
        "plain_dict_only: true",
    ]

    for phrase in required:
        assert phrase in text


def test_canonical_surface_contract_forbids_runtime_behavior() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    required = [
        "must not register hooks",
        "apply runtime binding",
        "invoke endpoints",
        "emit events",
        "mutate runtime state",
        "persist",
        "audit",
        "journal",
        "spawn subprocesses",
        "filesystem mutation paths",
        "call Scheduler, TaskRunner, Operator, Dispatcher, Supervisor, Native Runtime, Watchdog",
        "execute Recovery",
        "strict `__all__`",
        "exactly one public entry API",
    ]

    for phrase in required:
        assert phrase in text


def test_canonical_surface_contract_limits_ownership_to_public_interface() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    required = [
        "owns only the public Runtime Recovery interface",
        "recovery policy",
        "recovery planning",
        "recovery scheduling",
        "recovery execution",
        "recovery supervision",
        "recovery state machine",
        "recovery persistence",
        "recovery audit",
        "recovery journaling",
        "recovery hook registration",
        "recovery binding",
        "recovery endpoint invocation",
        "Those capabilities remain owned by their future dedicated packages",
        "may only validate, normalize, and forward canonical Runtime Recovery requests after future GO approval",
        "stable compatibility boundary",
        "must preserve its public API and ownership boundary",
        "Backward compatibility of the public Runtime Recovery surface must be maintained",
        "explicit major-version contract",
        "canonical_runtime_recovery_surface_v2",
        "silently replace, bypass, or deprecate this canonical surface",
        "All Runtime Recovery callers must remain compatible with it",
    ]

    for phrase in required:
        assert phrase in text
