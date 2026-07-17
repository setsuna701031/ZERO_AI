from pathlib import Path


WRAPPER_BOUNDARY = Path("docs/runtime_wrapper_boundary.md")
WRAPPER_GAP_INVENTORY = Path("docs/runtime_wrapper_gap_inventory.md")
WRAPPER_READINESS_REVIEW = Path("docs/runtime_wrapper_readiness_review.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
THIS_TEST = Path("tests/test_runtime_wrapper_boundary.py")

WRAPPER_GAPS = (
    "entrypoint design",
    "startup sequencing",
    "operator launch flow",
    "lifecycle connection",
    "deployment handoff",
)

INHERITED_SEALS = (
    "Release seal inherited.",
    "RC freeze inherited.",
    "Production entry inherited.",
    "Package boundary inherited.",
    "Assembly boundary inherited.",
    "Configuration boundary inherited.",
    "Environment resolver boundary inherited.",
)

WRAPPER_FORBIDDEN_AUTHORITY = (
    "Wrapper has no execution authority.",
    "Scheduler ownership forbidden.",
    "Executor ownership forbidden.",
    "Recovery activation forbidden.",
    "Runtime mutation forbidden.",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _wrapper_package_text() -> str:
    text = _text(PACKAGE_SEQUENCE)
    marker = "## Package 569"
    assert marker in text
    return text[text.index(marker) :]


def test_packages_569_to_576_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("569", "570", "571", "572", "573", "574", "575", "576"):
        assert f"## Package {package_number}" in text

    assert "Runtime Wrapper Boundary" in text
    assert "Documentation/test only." in text


def test_runtime_wrapper_docs_exist():
    assert WRAPPER_BOUNDARY.exists()
    assert WRAPPER_GAP_INVENTORY.exists()
    assert WRAPPER_READINESS_REVIEW.exists()


def test_inherited_seals_are_documented():
    for path in (WRAPPER_BOUNDARY, WRAPPER_READINESS_REVIEW):
        text = _text(path)
        for seal in INHERITED_SEALS:
            assert seal in text


def test_wrapper_has_no_execution_authority():
    for path in (WRAPPER_BOUNDARY, WRAPPER_GAP_INVENTORY, WRAPPER_READINESS_REVIEW):
        text = _text(path)
        assert "Wrapper has no execution authority." in text
        assert "Runtime execution forbidden." in text or path != WRAPPER_BOUNDARY


def test_scheduler_and_executor_ownership_forbidden():
    for path in (WRAPPER_BOUNDARY, WRAPPER_GAP_INVENTORY, WRAPPER_READINESS_REVIEW):
        text = _text(path)
        assert "Scheduler ownership forbidden." in text
        assert "Executor ownership forbidden." in text


def test_recovery_activation_and_runtime_mutation_forbidden():
    for path in (WRAPPER_BOUNDARY, WRAPPER_GAP_INVENTORY, WRAPPER_READINESS_REVIEW):
        text = _text(path)
        assert "Recovery activation forbidden." in text
        assert "Runtime mutation forbidden." in text


def test_wrapper_may_and_must_not_rules_are_documented():
    text = _text(WRAPPER_BOUNDARY)
    for phrase in (
        "Wrapper may validate readiness.",
        "Wrapper may collect environment status.",
        "Wrapper may prepare future entry contract.",
        "Wrapper may expose operator-facing boundary.",
        "Wrapper must not own scheduler.",
        "Wrapper must not own executor.",
        "Wrapper must not dispatch tasks.",
        "Wrapper must not execute plans.",
        "Wrapper must not activate recovery.",
        "Wrapper must not mutate runtime state.",
    ):
        assert phrase in text


def test_no_executable_entrypoint_artifacts_are_claimed():
    for path in (WRAPPER_BOUNDARY, WRAPPER_GAP_INVENTORY, WRAPPER_READINESS_REVIEW):
        text = _text(path)
        assert "No main.py is added." in text
        assert "No CLI commands are added." in text
        assert "No service startup is added." in text


def test_wrapper_gap_inventory_records_remaining_gaps_without_implementation():
    text = _text(WRAPPER_GAP_INVENTORY)
    assert "These gaps are not implemented by this package." in text
    for gap in WRAPPER_GAPS:
        assert gap in text
    assert text.count("Do not implement here") == len(WRAPPER_GAPS)


def test_readiness_review_has_go_no_go_and_required_guarantees():
    text = _text(WRAPPER_READINESS_REVIEW)
    assert "GO / NO-GO" in text
    assert "GO criteria:" in text
    assert "NO-GO criteria:" in text
    assert "Required Guarantees" in text
    for guarantee in WRAPPER_FORBIDDEN_AUTHORITY:
        assert guarantee in text


def test_no_runtime_imports_in_focused_test():
    lines = _text(THIS_TEST).splitlines()
    import_lines = [
        line
        for line in lines
        if line.startswith("import ") or line.startswith("from ")
    ]
    assert import_lines == ["from pathlib import Path"]


def test_package_sequence_records_scope_and_validation():
    text = _wrapper_package_text()
    assert "do not add main.py" in text
    assert "do not add CLI commands" in text
    assert "do not add service startup" in text
    assert "do not modify core/runtime" in text
    assert "do not modify scheduler" in text
    assert "do not modify executor" in text
    assert "do not enable recovery" in text
    assert "do not execute runtime logic" in text
    assert "do not mutate runtime state" in text
    assert "py -m pytest tests/test_runtime_wrapper_boundary.py -q" in text
    assert "do not run full suite, nightly, regression, or long validation" in text
