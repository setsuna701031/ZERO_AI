from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_single_entry_wiring_v1.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 167")
    end = text.find("## Package 168", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_single_entry_wiring_contract_exists():
    assert CONTRACT.exists()


def test_single_entry_wiring_contract_required_sections_exist():
    text = _text(CONTRACT)
    for section in (
        "## Purpose",
        "## Single Entry Rule",
        "## Required Upstream Boundary",
        "## Declarative Wiring Plan",
        "## Preserved Package Boundaries",
        "## Canonical Event Requirement",
        "## GO / NO-GO",
        "## Next Package",
    ):
        assert section in text


def test_single_entry_wiring_contract_preserves_boundaries_and_gate_off():
    text = _text(CONTRACT)
    assert "`runtime_recovery_single_entry`" in text
    assert "No package in this scope may wire multiple runtime surfaces" in text
    assert "aer.runtime.recovery.controlled_activation_report.v1" in text
    assert "Packages 155 through 166 remain passive and preparatory" in text
    assert "Package 163 through Package 166 gate OFF semantics remain intact" in text
    assert "Prepared controlled activation data is not permission to activate Recovery" in text


def test_single_entry_wiring_contract_requires_canonical_event_schema():
    text = _text(CONTRACT)
    for field in ("`source_surface`", "`entry_id`", "`route_id`", "`gate_state`"):
        assert field in text
    assert "Different future sources must not invent separate event shapes" in text


def test_single_entry_wiring_contract_go_no_go_and_sequence_entry():
    text = _text(CONTRACT)
    assert "Final decision: GO" in text
    assert "Next package: Package 168" in text

    entry = _package_entry()
    assert "## Package 167" in entry
    assert "Runtime Recovery Single Entry Wiring Contract" in entry
    assert "docs/contracts/runtime/recovery_single_entry_wiring_v1.md" in entry
    assert "tests/test_runtime_recovery_single_entry_wiring_contract.py" in entry
    assert "python -m pytest tests/test_runtime_recovery_single_entry_wiring_contract.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 168" in entry


def test_single_entry_wiring_contract_has_no_implementation_tokens():
    text = _text(CONTRACT)
    for token in (
        "def ",
        "class ",
        "import ",
        "scheduler.",
        "operator.",
        "dispatcher.",
        "supervisor.",
        "native_runtime.",
        "subprocess.",
        "open(",
        ".write(",
        "Path(",
    ):
        assert token not in text
