from pathlib import Path


REVIEW = Path("docs/runtime_recovery_canonical_response_readiness_review.md")
SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


PACKAGE_TITLES = {
    247: "Canonical Runtime Recovery Response Contract",
    248: "Canonical Runtime Recovery Response Helper",
    249: "Canonical Runtime Recovery Response Report",
    250: "Canonical Runtime Recovery Response Readiness Review",
}


def test_readiness_review_exists_and_pins_disabled_response_layer() -> None:
    text = REVIEW.read_text(encoding="utf-8")
    required = [
        "Package 250",
        "aer.runtime.recovery.canonical_response.v1",
        "completely disabled, deterministic, non-executing, non-mutating",
        "not connected to Runtime execution",
        "Public API is `prepare_canonical_runtime_recovery_response(...)`",
        "ONLY public Runtime Recovery response object",
        "Only the Canonical Runtime Recovery Surface may publicly return Canonical Runtime Recovery Response objects",
        "No public API may bypass the Canonical Surface and expose responses directly",
        "Request helper is never a Runtime entry point",
        "Response helper is never a Runtime entry point",
        "Surface is the only public Runtime Recovery entry",
        "Surface is the only public component allowed to accept Request and return Response",
        "Focused seal tests only",
        "Final decision: GO",
    ]

    for phrase in required:
        assert phrase in text


def test_readiness_review_lists_hard_rules() -> None:
    text = REVIEW.read_text(encoding="utf-8")
    required = [
        "The response represents observation only",
        "must not execute, authorize, schedule, dispatch, mutate, or recover",
        "does not call Binding Endpoint",
        "does not call Activation Gate",
        "does not call Canonical Surface",
        "does not call the Request helper",
        "No Runtime wiring is introduced",
        "Scheduler is not changed",
        "TaskRunner is not changed",
        "Operator is not changed",
        "Dispatcher is not changed",
        "Supervisor is not changed",
        "Native Runtime is not changed",
        "Watchdog is not changed",
        "Recovery is not executed",
        "Runtime state is not mutated",
        "Filesystem paths are not mutated",
        "Subprocess paths are not called",
        "Audit paths are not called",
        "Journal paths are not called",
        "Persistence paths are not called",
    ]

    for phrase in required:
        assert phrase in text


def test_package_sequence_extends_247_through_250_only() -> None:
    text = SEQUENCE.read_text(encoding="utf-8")
    start = text.index("## Package 247")
    end = text.find("## Package 251", start)
    section = text[start:] if end == -1 else text[start:end]

    for package_id, title in PACKAGE_TITLES.items():
        assert f"## Package {package_id}" in section
        assert f"Package {package_id}: {title}" in section

    assert "## Package 251" not in section
    assert "Final decision: GO. Next package: Package 251." in section


def test_package_sequence_pins_response_boundaries_and_non_mainline_reporting() -> None:
    text = SEQUENCE.read_text(encoding="utf-8")
    section = text[text.index("## Package 247") :]
    required = [
        "No Runtime wiring",
        "No Scheduler changes",
        "No TaskRunner changes",
        "No Operator changes",
        "No Dispatcher changes",
        "No Supervisor changes",
        "No Native Runtime changes",
        "No Watchdog changes",
        "No Binding Endpoint calls",
        "No Activation Gate calls",
        "No Canonical Surface calls",
        "No Request helper calls",
        "No Recovery execution",
        "No runtime mutation",
        "No filesystem, subprocess, audit, journal, or persistence behavior",
        "Long validation must not be run by Codex",
        "Exactly one public response API",
        "Exactly one canonical response schema",
        "ONLY public Runtime Recovery response object",
        "No additional public response APIs may ever be introduced",
        "No public API may bypass the Canonical Surface and expose responses directly",
        "Request helper is never a Runtime entry point",
        "Response helper is never a Runtime entry point",
        "Surface is the only public Runtime Recovery entry",
        "Surface is the only public component allowed to accept Request and return Response",
        "append-only schema",
        "observation only",
        "## Non-mainline Issues Found",
    ]

    for phrase in required:
        assert phrase in section
