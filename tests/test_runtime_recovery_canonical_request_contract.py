from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/canonical_runtime_recovery_request_v1.md")


def test_canonical_request_contract_exists_and_names_schema() -> None:
    text = CONTRACT.read_text(encoding="utf-8")

    assert "aer.runtime.recovery.canonical_request.v1" in text
    assert "first canonical request layer" in text
    assert "does not wire requests into the Canonical Runtime Recovery Surface yet" in text
    assert "No existing runtime caller may import or call the request helper" in text
    assert "owned by the Canonical Surface family" in text
    assert "must not connect the request helper to the surface helper yet" in text
    assert "Connection happens only after a future GO review" in text


def test_canonical_request_contract_pins_required_fields() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    required = [
        "schema: aer.runtime.recovery.canonical_request.v1",
        "request_id",
        "surface_id",
        "runtime_identity",
        "recovery_reason",
        "recovery_mode",
        "recovery_context",
        "disabled: true",
        "execution_allowed: false",
        "recovery_enabled: false",
        "runtime_state_mutated: false",
        "surface_wired: false",
        "owned_by_canonical_surface_family: true",
        "request_helper_connected_to_surface_helper: false",
        "surface_connection_requires_future_go_review: true",
        "canonical_surface_called: false",
        "runtime_caller_modified: false",
        "public_compatibility_boundary: true",
        "append_only_public_schema: true",
        "existing_public_fields_renamable: false",
        "existing_public_fields_removable: false",
        "future_fields_must_be_optional: true",
        "major_version_required_for_breaking_schema_change: true",
        "exactly_one_canonical_request_schema: true",
        "competing_public_request_formats_allowed: false",
        "future_implementations_must_consume_this_request: true",
        "intent_only: true",
        "execution_request: false",
        "plain_dict_only: true",
    ]

    for phrase in required:
        assert phrase in text


def test_canonical_request_contract_forbids_runtime_behavior() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    required = [
        "must not import runtime execution modules",
        "call the Canonical Runtime Recovery Surface",
        "register hooks",
        "apply binding",
        "invoke endpoints",
        "mutate runtime state",
        "persist",
        "audit",
        "journal",
        "spawn subprocesses",
        "filesystem mutation paths",
        "call Scheduler, TaskRunner, Operator, Dispatcher, Supervisor, Native Runtime, Watchdog",
        "execute Recovery",
        "strict `__all__`",
        "exactly one public API",
        "Everything else must remain private",
        "must not expose alternate request builders",
        "legacy compatibility builders",
        "convenience wrappers",
        "alias APIs",
        "Future packages must extend this API instead of creating additional public request entry points",
    ]

    for phrase in required:
        assert phrase in text


def test_canonical_request_contract_pins_public_compatibility_rules() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    required = [
        "part of the public compatibility boundary",
        "public request schema is append-only",
        "Existing public fields must never be renamed or removed",
        "only add optional fields unless a major-version contract",
        "canonical_runtime_recovery_request_v2",
        "Exactly one canonical public request schema is allowed",
        "must not introduce competing public Runtime Recovery request formats",
        "must consume this public request object instead of inventing additional request schemas",
        "represents intent only",
        "not an execution request",
        "normalize and validate request data only",
        "must not import runtime execution modules",
        "decide recovery policy",
        "schedule recovery",
        "execute recovery",
        "invoke runtime",
        "call canonical surface",
        "call binding endpoint",
        "call activation gate",
    ]

    for phrase in required:
        assert phrase in text
