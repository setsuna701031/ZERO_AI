from pathlib import Path


PLAN = Path("docs/runtime_recovery_controlled_wiring_phase_plan.md")
SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


PACKAGE_TITLES = {
    223: "Runtime Recovery Controlled Wiring Phase Plan",
    224: "Runtime Recovery Controlled Wiring Contract",
    225: "Runtime Recovery Controlled Wiring Helper",
    226: "Runtime Recovery Controlled Wiring Report",
    227: "Runtime Recovery Controlled Wiring Admission",
    228: "Runtime Recovery Controlled Wiring Verification",
    229: "Runtime Recovery Controlled Wiring Dry Run",
    230: "Runtime Recovery Controlled Wiring GO Review",
}


HARD_RULES = [
    "Recovery is not executed",
    "Recovery is not enabled",
    "Runtime state is not mutated",
    "Runtime hooks are not registered",
    "Runtime binding is not applied",
    "Endpoints are not invoked",
    "Scheduler is not called",
    "TaskRunner is not called",
    "Operator is not called",
    "Dispatcher is not called",
    "Supervisor is not called",
    "Native Runtime is not called",
    "Watchdog is not called",
    "Audit is not called",
    "Journal is not called",
    "Persistence is not called",
    "Subprocess paths are not called",
    "Filesystem mutation paths are not called",
    "documentation + seal only",
    "planning/contract/governance only",
    "Actual runtime wiring begins only after Package 230 receives GO",
]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_controlled_wiring_phase_plan_exists_and_lists_packages() -> None:
    text = _text(PLAN)

    assert "Package 223: Runtime Recovery Controlled Wiring Phase Plan" in text
    assert "Packages 223 through 230 define the Runtime Recovery Controlled Wiring Phase" in text

    for package_id, title in PACKAGE_TITLES.items():
        assert f"Package {package_id}: {title}" in text


def test_controlled_wiring_phase_plan_seals_hard_rules() -> None:
    text = _text(PLAN)

    for rule in HARD_RULES:
        assert rule in text

    assert "Final decision: GO for Package 223" in text
    assert "NO-GO for Recovery execution" in text
    assert "Package 224" in text


def test_package_sequence_extends_after_222_through_230() -> None:
    text = _text(SEQUENCE)
    package_222 = text.index("## Package 222")

    previous = package_222
    for package_id, title in PACKAGE_TITLES.items():
        marker = f"## Package {package_id}"
        assert marker in text
        assert f"Package {package_id}: {title}" in text
        current = text.index(marker)
        assert current > previous
        previous = current


def test_package_sequence_keeps_controlled_wiring_disabled() -> None:
    text = _text(SEQUENCE)
    controlled_wiring_section = text[text.index("## Package 223") :]

    for rule in HARD_RULES:
        assert rule in controlled_wiring_section

    required_denials = [
        "Do not execute Recovery",
        "Do not enable Recovery",
        "Do not mutate runtime state",
        "Do not register runtime hooks",
        "Do not apply runtime binding",
        "Do not invoke endpoints",
        "Do not call Scheduler, TaskRunner, Operator, Dispatcher, Supervisor, Native Runtime, Watchdog, Audit, Journal, Persistence, subprocess, or filesystem mutation paths",
        "This package is documentation + seal only",
    ]
    for denial in required_denials:
        assert denial in controlled_wiring_section


def test_non_mainline_issue_reporting_is_explicit() -> None:
    plan_text = _text(PLAN)
    sequence_text = _text(SEQUENCE)

    assert "## Non-mainline Issues Found" in plan_text
    assert "Package 210 wording" in plan_text
    assert "Package 222" in plan_text
    assert "## Non-mainline Issues Found" in sequence_text[sequence_text.index("## Package 223") :]
