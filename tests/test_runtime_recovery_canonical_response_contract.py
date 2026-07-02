from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/canonical_runtime_recovery_response_v1.md")


def test_canonical_response_contract_exists_and_names_schema() -> None:
    text = CONTRACT.read_text(encoding="utf-8")

    assert "aer.runtime.recovery.canonical_response.v1" in text
    assert "canonical response layer" in text
    assert "completely disabled, deterministic, non-executing, non-mutating" in text
    assert "not connected to Runtime execution" in text


def test_canonical_response_contract_pins_public_api_and_compatibility() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    required = [
        "prepare_canonical_runtime_recovery_response(...)",
        "strict `__all__`",
        "exactly one public API",
        "Everything else remains private",
        "append-only",
        "backward compatible",
        "canonical_runtime_recovery_response_v2",
        "Exactly one public response API is allowed",
        "Exactly one canonical response schema is allowed",
        "must not introduce competing public Runtime Recovery response formats",
        "ONLY public Runtime Recovery response object",
        "must return this response shape instead of introducing new public response DTOs",
        "Only the Canonical Runtime Recovery Surface may publicly return Canonical Runtime Recovery Response objects",
        "must return this canonical response through the Canonical Runtime Recovery Surface",
        "No future package may construct or expose public Runtime Recovery responses directly",
        "No additional public response APIs may ever be introduced",
        "No public API may bypass the Canonical Surface and expose responses directly",
        "Existing public fields may never be removed or renamed",
        "canonical_runtime_recovery_response_v2",
    ]

    for phrase in required:
        assert phrase in text


def test_canonical_response_contract_pins_required_fields_and_observation_only() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    required = [
        "schema: aer.runtime.recovery.canonical_response.v1",
        "response_id",
        "request_id",
        "surface_id",
        "runtime_identity",
        "accepted",
        "execution_allowed: false",
        "recovery_enabled: false",
        "status",
        "reason",
        "diagnostics",
        "timestamp",
        "observation_only: true",
        "runtime_state_mutated: false",
        "plain_dict_only: true",
        "only_public_runtime_recovery_response_object: true",
        "future_packages_must_return_this_shape: true",
        "only_surface_may_publicly_return_response: true",
        "future_implementations_return_through_canonical_surface: true",
        "public_direct_response_exposure_allowed: false",
        "additional_public_response_apis_allowed: false",
        "response_helper_internal_compatibility_artifact: true",
        "standalone_runtime_entry_point: false",
        "response_helper_public_runtime_entry_point: false",
        "canonical_surface_bypass_allowed: false",
        "must not execute, authorize, schedule, dispatch, mutate, or recover",
    ]

    for phrase in required:
        assert phrase in text


def test_canonical_response_contract_limits_surface_and_helper_ownership() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    required = [
        "The Canonical Runtime Recovery Surface owns",
        "public Runtime Recovery entry",
        "request admission",
        "request normalization",
        "response return",
        "The Canonical Runtime Recovery Surface does not own",
        "recovery execution",
        "recovery planning",
        "recovery scheduling",
        "recovery supervision",
        "recovery state machine",
        "recovery persistence",
        "recovery audit",
        "recovery journal",
        "internal compatibility artifact of the Canonical Surface family",
        "not a standalone Runtime entry point",
        "never a public Runtime entry point",
        "owns only",
        "response normalization",
        "response validation",
        "response compatibility",
        "does NOT own",
        "execution",
        "planning",
        "scheduling",
        "recovery policy",
        "recovery state",
        "runtime mutation",
        "dispatcher",
        "operator",
        "supervisor",
        "watchdog",
        "persistence",
        "audit",
        "journal",
    ]

    for phrase in required:
        assert phrase in text


def test_canonical_response_contract_forbids_runtime_behavior() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    required = [
        "must not execute Recovery",
        "authorize Recovery",
        "schedule Recovery",
        "dispatch Recovery",
        "mutate runtime state",
        "call canonical surface",
        "call request helper",
        "call binding endpoint",
        "call activation gate",
        "persist",
        "audit",
        "journal",
        "spawn subprocesses",
        "filesystem mutation paths",
        "call Scheduler, TaskRunner, Operator, Dispatcher, Supervisor, Native Runtime, or Watchdog",
    ]

    for phrase in required:
        assert phrase in text
