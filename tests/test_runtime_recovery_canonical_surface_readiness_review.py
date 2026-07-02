from pathlib import Path


REVIEW = Path("docs/runtime_recovery_canonical_surface_readiness_review.md")
SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


PACKAGE_TITLES = {
    239: "Canonical Runtime Recovery Surface Contract",
    240: "Canonical Runtime Recovery Surface Helper",
    241: "Canonical Runtime Recovery Surface Report",
    242: "Canonical Runtime Recovery Surface Readiness Review",
}


def test_readiness_review_exists_and_pins_single_canonical_surface() -> None:
    text = REVIEW.read_text(encoding="utf-8")
    required = [
        "Package 242",
        "runtime_recovery_canonical_surface",
        "Exactly one canonical Runtime Recovery surface",
        "ONLY public Runtime Recovery entry surface",
        "Exactly one public entry API",
        "No competing public Runtime Recovery surfaces",
        "All future Runtime Recovery implementations, beginning with Packages 243 and later, must enter through this surface",
        "No future package may expose another public Runtime Recovery entry API",
        "may only connect to this canonical surface in future packages after the required GO reviews",
        "Multiple Runtime Recovery entry points are not allowed",
        "must flow through the single canonical surface",
        "must not introduce competing Runtime entry paths",
        "No existing runtime module imports or calls the canonical surface",
        "Final decision: GO",
    ]

    for phrase in required:
        assert phrase in text


def test_readiness_review_limits_canonical_surface_ownership() -> None:
    text = REVIEW.read_text(encoding="utf-8")
    required = [
        "owns the public Runtime Recovery interface only",
        "does not own recovery policy, planning, scheduling, execution, supervision, state machine, persistence, audit, journaling, hook registration, binding, or endpoint invocation",
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


def test_readiness_review_forbids_runtime_behavior() -> None:
    text = REVIEW.read_text(encoding="utf-8")
    required = [
        "`core/runtime/runtime_supervisor_bridge.py` is not changed",
        "Scheduler is not changed",
        "TaskRunner is not changed",
        "Operator is not changed",
        "Dispatcher is not changed",
        "Supervisor is not changed",
        "Native Runtime is not changed",
        "Watchdog is not changed",
        "Recovery is not executed",
        "Recovery is not enabled",
        "Runtime hooks are not registered",
        "Runtime binding is not applied",
        "Endpoints are not invoked",
        "Events are not emitted",
        "Runtime state is not mutated",
        "Persistence paths are not called",
        "Audit paths are not called",
        "Journal paths are not called",
        "Subprocess paths are not called",
        "Filesystem mutation paths are not called",
        "Focused seal tests only",
    ]

    for phrase in required:
        assert phrase in text


def test_package_sequence_extends_239_through_242_only() -> None:
    text = SEQUENCE.read_text(encoding="utf-8")
    section = text[text.index("## Package 239") :]

    for package_id, title in PACKAGE_TITLES.items():
        assert f"## Package {package_id}" in section
        assert f"Package {package_id}: {title}" in section

    assert "## Package 243" not in section
    assert "Final decision: GO. Next package: Package 243." in section


def test_package_sequence_pins_no_wiring_and_non_mainline_reporting() -> None:
    text = SEQUENCE.read_text(encoding="utf-8")
    section = text[text.index("## Package 239") :]
    required = [
        "Exactly ONE canonical Runtime Recovery surface",
        "The Canonical Runtime Recovery Surface introduced in Package 239 is the ONLY public Runtime Recovery entry surface",
        "No future package may expose another public Runtime Recovery entry API",
        "Bridge modules, adapters, supervisors, schedulers, operators, dispatchers, watchdogs, and native runtime components may only connect to this canonical surface in future packages after the required GO reviews",
        "The Canonical Runtime Recovery Surface owns the public Runtime Recovery interface only",
        "The Canonical Runtime Recovery Surface is a stable compatibility boundary",
        "No future package may silently replace, bypass, or deprecate this canonical surface",
        "Do not create multiple Runtime Recovery entry points",
        "No existing runtime module may import or call it in this package",
        "No changes to `core/runtime/runtime_supervisor_bridge.py` yet",
        "Do not execute Recovery",
        "Do not enable Recovery",
        "Do not register hooks",
        "Do not apply runtime binding",
        "Do not invoke endpoints",
        "Do not emit events",
        "Do not mutate runtime state",
        "No persistence, audit, journal, subprocess, or filesystem mutation paths",
        "Long validation must not be run by Codex",
        "focused seal tests only",
        "## Non-mainline Issues Found",
    ]

    for phrase in required:
        assert phrase in section
