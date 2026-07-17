from pathlib import Path


REVIEW = Path("docs/runtime_recovery_canonical_request_readiness_review.md")
SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


PACKAGE_TITLES = {
    243: "Canonical Runtime Recovery Request Contract",
    244: "Canonical Runtime Recovery Request Helper",
    245: "Canonical Runtime Recovery Request Report",
    246: "Canonical Runtime Recovery Request Readiness Review",
}


def test_readiness_review_exists_and_pins_disabled_request_layer() -> None:
    text = REVIEW.read_text(encoding="utf-8")
    required = [
        "Package 246",
        "aer.runtime.recovery.canonical_request.v1",
        "disabled, plain-data, non-executing",
        "not wired into any runtime caller",
        "not wired into the Canonical Runtime Recovery Surface yet",
        "owned by the Canonical Surface family",
        "do not connect the request helper to the surface helper yet",
        "Connection happens only after a future GO review",
        "public compatibility boundary",
        "append-only",
        "Existing public fields must never be renamed or removed",
        "canonical_runtime_recovery_request_v2",
        "Exactly one canonical public request schema is allowed",
        "competing public Runtime Recovery request formats",
        "must consume this public request object instead of inventing additional request schemas",
        "intent only",
        "not an execution request",
        "normalizes and validates request data only",
        "exposes exactly one public API",
        "Strict `__all__`",
        "no alternate request builders, legacy compatibility builders, convenience wrappers, or alias APIs",
        "Future packages must extend this API instead of creating additional public request entry points",
        "Focused seal tests only",
        "Final decision: GO",
    ]

    for phrase in required:
        assert phrase in text


def test_readiness_review_lists_stable_fields_and_hard_rules() -> None:
    text = REVIEW.read_text(encoding="utf-8")
    required = [
        "`schema`",
        "`request_id`",
        "`surface_id`",
        "`runtime_identity`",
        "`recovery_reason`",
        "`recovery_mode`",
        "`recovery_context`",
        "`disabled`",
        "`execution_allowed`",
        "`recovery_enabled`",
        "`runtime_state_mutated`",
        "`core/runtime/runtime_supervisor_bridge.py` is not modified",
        "Recovery is not executed",
        "Recovery is not enabled",
        "Hooks are not registered",
        "Binding is not applied",
        "Endpoints are not invoked",
        "Runtime state is not mutated",
        "does not decide recovery policy, schedule recovery, execute recovery, invoke runtime, mutate runtime state, call canonical surface, call binding endpoint, or call activation gate",
        "Scheduler is not changed",
        "TaskRunner is not changed",
        "Operator is not changed",
        "Dispatcher is not changed",
        "Supervisor is not changed",
        "Native Runtime is not changed",
        "Watchdog is not changed",
        "Persistence paths are not called",
        "Audit paths are not called",
        "Journal paths are not called",
        "Subprocess paths are not called",
        "Filesystem mutation paths are not called",
    ]

    for phrase in required:
        assert phrase in text


def test_package_sequence_extends_243_through_246_only() -> None:
    text = SEQUENCE.read_text(encoding="utf-8")
    start = text.index("## Package 243")
    section = text[start:text.index("## Package 247", start)]

    for package_id, title in PACKAGE_TITLES.items():
        assert f"## Package {package_id}" in section
        assert f"Package {package_id}: {title}" in section

    assert "## Package 247" not in section
    assert "Final decision: GO. Next package: Package 247." in section


def test_package_sequence_pins_no_wiring_and_non_mainline_reporting() -> None:
    text = SEQUENCE.read_text(encoding="utf-8")
    section = text[text.index("## Package 243") :]
    required = [
        "Do not wire into Canonical Surface yet",
        "owned by the Canonical Surface family",
        "must not connect the request helper to the surface helper yet",
        "Connection happens only after a future GO review",
        "public request schema is append-only",
        "Exactly one canonical public request schema is allowed",
        "must not introduce competing public Runtime Recovery request formats",
        "exactly one public API",
        "additional public request entry points",
        "Do not modify existing runtime callers",
        "Do not modify `core/runtime/runtime_supervisor_bridge.py`",
        "Do not execute Recovery",
        "Do not enable Recovery",
        "Do not register hooks",
        "Do not apply binding",
        "Do not invoke endpoints",
        "Do not mutate runtime state",
        "No Scheduler, TaskRunner, Operator, Dispatcher, Supervisor, Native Runtime, or Watchdog changes",
        "No persistence, audit, journal, subprocess, or filesystem mutation paths",
        "Long validation must not be run by Codex",
        "## Non-mainline Issues Found",
    ]

    for phrase in required:
        assert phrase in section
