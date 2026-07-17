from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_single_entry_binding_v1.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 171")
    end = text.find("## Package 172", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_single_entry_binding_contract_exists():
    assert CONTRACT.exists()


def test_single_entry_binding_contract_required_sections_exist():
    text = _text(CONTRACT)
    for section in (
        "## Purpose",
        "## Single Entry Binding Rule",
        "## Required Upstream Boundary",
        "## Binding Defaults",
        "## Preserved Boundaries",
        "## Denied Capabilities",
        "## GO / NO-GO",
        "## Next Package",
    ):
        assert section in text


def test_single_entry_binding_contract_preserves_single_entry_and_schema():
    text = _text(CONTRACT)
    assert "`runtime_recovery_single_entry`" in text
    assert "No other runtime entry surface may be bound, aliased, or substituted" in text
    assert "Package 169 canonical event schema remains intact" in text
    for field in ("`source_surface`", "`entry_id`", "`route_id`", "`gate_state`", "`event_emitted`"):
        assert field in text


def test_single_entry_binding_contract_defaults_are_safe():
    text = _text(CONTRACT)
    for phrase in (
        "`dry_run` as `true`",
        "`bound_to_runtime` as `false`",
        "`binding_enabled` as `false`",
        "`route_enabled` as `false`",
        "`event_emitted` as `false`",
        "`recovery_enabled` as `false`",
        "`executes_recovery` as `false`",
        "`side_effects_performed` as `false`",
        "Prepared binding data is not permission to activate Recovery",
    ):
        assert phrase in text


def test_single_entry_binding_contract_go_no_go_and_sequence_entry():
    text = _text(CONTRACT)
    assert "Final decision: GO" in text
    assert "Next package: Package 172" in text

    entry = _package_entry()
    assert "## Package 171" in entry
    assert "Runtime Recovery Single Entry Binding Contract" in entry
    assert "docs/contracts/runtime/recovery_single_entry_binding_v1.md" in entry
    assert "tests/test_runtime_recovery_single_entry_binding_contract.py" in entry
    assert "python -m pytest tests/test_runtime_recovery_single_entry_binding_contract.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 172" in entry


def test_single_entry_binding_contract_has_no_implementation_tokens():
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
