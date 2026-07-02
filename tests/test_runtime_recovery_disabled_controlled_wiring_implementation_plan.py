from pathlib import Path


PLAN = Path("docs/runtime_recovery_disabled_controlled_wiring_implementation_plan.md")
SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


PACKAGE_TITLES = {
    231: "Runtime Recovery Disabled Controlled Wiring Implementation Plan",
    232: "Disabled Controlled Wiring Contract",
    233: "Disabled Controlled Wiring Helper",
    234: "Disabled Controlled Wiring Report",
    235: "Disabled Controlled Wiring Admission Helper",
    236: "Disabled Controlled Wiring Verification Helper",
    237: "Disabled Controlled Wiring Dry Run Helper",
    238: "Disabled Controlled Wiring Readiness Review",
}


HARD_RULES = [
    "Packages 231 through 238 are the final documentation/governance phase before Runtime implementation",
    "Runtime wiring surfaces may be introduced only after Package 238, beginning with Package 239 as disabled plain-data helpers",
    "Package 239 begins the first disabled Runtime implementation surface, still non-executing and fully gated",
    "Package 239 must introduce exactly one canonical Runtime implementation surface",
    "Package 239 must not create multiple parallel Runtime entry points",
    "All future Runtime Recovery execution, when eventually enabled, must flow through this single canonical surface",
    "Future packages may extend or verify that surface, but must not introduce competing Runtime entry paths",
    "No change to `core/runtime/runtime_supervisor_bridge.py` yet",
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
    "Long validation must not be run by Codex",
    "Focused seal only",
]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_disabled_controlled_wiring_plan_exists_and_lists_packages() -> None:
    text = _text(PLAN)

    assert "Package 231: Runtime Recovery Disabled Controlled Wiring Implementation Plan" in text
    assert "Packages 231 through 238 are the final documentation/governance phase before Runtime implementation" in text

    for package_id, title in PACKAGE_TITLES.items():
        assert f"Package {package_id}: {title}" in text


def test_disabled_controlled_wiring_plan_seals_hard_rules() -> None:
    text = _text(PLAN)

    for rule in HARD_RULES:
        assert rule in text

    assert "Final decision: GO for Package 231" in text
    assert "NO-GO for Runtime behavior changes" in text
    assert "Package 232" in text


def test_package_sequence_extends_after_230_through_238() -> None:
    text = _text(SEQUENCE)
    package_230 = text.index("## Package 230")

    previous = package_230
    for package_id, title in PACKAGE_TITLES.items():
        marker = f"## Package {package_id}"
        assert marker in text
        assert f"Package {package_id}: {title}" in text
        current = text.index(marker)
        assert current > previous
        previous = current


def test_package_sequence_keeps_disabled_implementation_non_runtime() -> None:
    text = _text(SEQUENCE)
    section = text[text.index("## Package 231") :]

    for rule in HARD_RULES:
        assert rule in section

    required_denials = [
        "Do not execute Recovery",
        "Do not enable Recovery",
        "Do not register hooks",
        "Do not apply runtime binding",
        "Do not invoke endpoints",
        "Do not emit events",
        "Do not mutate runtime state",
        "No persistence, audit, journal, subprocess, or filesystem mutation paths",
        "Focused seal only",
    ]
    for denial in required_denials:
        assert denial in section


def test_package_238_points_to_239_and_non_mainline_reporting_is_explicit() -> None:
    plan_text = _text(PLAN)
    sequence_text = _text(SEQUENCE)
    section = sequence_text[sequence_text.index("## Package 231") :]

    assert "## Non-mainline Issues Found" in plan_text
    assert "Package 210 wording" in plan_text
    assert "Package 222" in plan_text
    assert "Final decision: GO. Next package: Package 239." in section
    assert "## Package 239" not in section
    assert "Package 239 begins the first disabled Runtime implementation surface, still non-executing and fully gated" in section
    assert "Package 239 must introduce exactly one canonical Runtime implementation surface" in section
    assert "multiple parallel Runtime entry points" in section
    assert "single canonical surface" in section
    assert "competing Runtime entry paths" in section
    assert "## Non-mainline Issues Found" in section
