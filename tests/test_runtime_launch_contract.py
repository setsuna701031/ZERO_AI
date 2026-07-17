from pathlib import Path


LAUNCH_CONTRACT = Path("docs/runtime_launch_contract.md")
LAUNCH_GAP_INVENTORY = Path("docs/runtime_launch_gap_inventory.md")
LAUNCH_READINESS_REVIEW = Path("docs/runtime_launch_readiness_review.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
THIS_TEST = Path("tests/test_runtime_launch_contract.py")

LAUNCH_GAPS = (
    "executable entry creation",
    "runtime boot sequence",
    "operator approval flow",
    "deployment connection",
    "lifecycle activation",
)

INHERITED_SEALS = (
    "Release seal inherited.",
    "RC freeze inherited.",
    "Production entry inherited.",
    "Package boundary inherited.",
    "Assembly boundary inherited.",
    "Configuration boundary inherited.",
    "Environment resolver boundary inherited.",
    "Wrapper boundary inherited.",
)

LAUNCH_GUARANTEES = (
    "Launch is contract only.",
    "Launch contract has no execution authority.",
    "Scheduler ownership forbidden.",
    "Executor ownership forbidden.",
    "Operator approval required before any future launch execution.",
    "Recovery activation forbidden.",
    "Runtime mutation forbidden.",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _launch_package_text() -> str:
    text = _text(PACKAGE_SEQUENCE)
    marker = "## Package 577"
    assert marker in text
    return text[text.index(marker) :]


def test_packages_577_to_584_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("577", "578", "579", "580", "581", "582", "583", "584"):
        assert f"## Package {package_number}" in text

    assert "Runtime Launch Contract Boundary" in text
    assert "Documentation/test only." in text


def test_runtime_launch_docs_exist():
    assert LAUNCH_CONTRACT.exists()
    assert LAUNCH_GAP_INVENTORY.exists()
    assert LAUNCH_READINESS_REVIEW.exists()


def test_inherited_seals_are_documented():
    for path in (LAUNCH_CONTRACT, LAUNCH_READINESS_REVIEW):
        text = _text(path)
        for seal in INHERITED_SEALS:
            assert seal in text


def test_launch_is_contract_only_with_no_execution_authority():
    for path in (LAUNCH_CONTRACT, LAUNCH_GAP_INVENTORY, LAUNCH_READINESS_REVIEW):
        text = _text(path)
        assert "Launch is contract only." in text
        assert "Launch contract has no execution authority." in text


def test_scheduler_and_executor_ownership_forbidden():
    for path in (LAUNCH_CONTRACT, LAUNCH_GAP_INVENTORY, LAUNCH_READINESS_REVIEW):
        text = _text(path)
        assert "Scheduler ownership forbidden." in text
        assert "Executor ownership forbidden." in text


def test_operator_approval_required_and_not_bypassed():
    text = _text(LAUNCH_CONTRACT)
    assert "Operator approval required before any future launch execution." in text
    assert "Operator approval boundary remains in force." in text
    assert "Launch contract must not bypass operator." in text
    assert "Operator bypass forbidden." in text

    for path in (LAUNCH_GAP_INVENTORY, LAUNCH_READINESS_REVIEW):
        assert "Operator approval required before any future launch execution." in _text(path)


def test_recovery_disabled_and_activation_forbidden():
    for path in (LAUNCH_CONTRACT, LAUNCH_GAP_INVENTORY, LAUNCH_READINESS_REVIEW):
        text = _text(path)
        assert "Recovery activation forbidden." in text
        assert "Recovery remains disabled." in text or path == LAUNCH_GAP_INVENTORY


def test_runtime_mutation_forbidden():
    for path in (LAUNCH_CONTRACT, LAUNCH_GAP_INVENTORY, LAUNCH_READINESS_REVIEW):
        text = _text(path)
        assert "Runtime mutation forbidden." in text
        assert "runtime mutation occurs" in text or path != LAUNCH_READINESS_REVIEW


def test_launch_may_and_must_not_rules_are_documented():
    text = _text(LAUNCH_CONTRACT)
    for phrase in (
        "Launch contract may define startup order.",
        "Launch contract may define required checks.",
        "Launch contract may define handoff points.",
        "Launch contract may describe future entry behavior.",
        "Launch contract must not execute startup.",
        "Launch contract must not own scheduler.",
        "Launch contract must not own executor.",
        "Launch contract must not bypass operator.",
        "Launch contract must not activate recovery.",
        "Launch contract must not mutate runtime.",
    ):
        assert phrase in text


def test_no_executable_launcher_artifacts_are_claimed():
    for path in (LAUNCH_CONTRACT, LAUNCH_GAP_INVENTORY, LAUNCH_READINESS_REVIEW):
        text = _text(path)
        assert "No main.py is added." in text
        assert "No start scripts are added." in text
        assert "No CLI execution commands are added." in text


def test_launch_gap_inventory_records_remaining_gaps_without_implementation():
    text = _text(LAUNCH_GAP_INVENTORY)
    assert "These gaps are not implemented by this package." in text
    for gap in LAUNCH_GAPS:
        assert gap in text
    assert text.count("Do not implement here") == len(LAUNCH_GAPS)


def test_readiness_review_has_go_no_go_and_required_guarantees():
    text = _text(LAUNCH_READINESS_REVIEW)
    assert "GO / NO-GO Criteria" in text
    assert "GO criteria:" in text
    assert "NO-GO criteria:" in text
    assert "Required Guarantees" in text
    for guarantee in LAUNCH_GUARANTEES:
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
    text = _launch_package_text()
    assert "do not add main.py" in text
    assert "do not add start scripts" in text
    assert "do not add CLI execution commands" in text
    assert "do not modify core/runtime" in text
    assert "do not modify scheduler" in text
    assert "do not modify executor" in text
    assert "do not connect services" in text
    assert "do not start runtime loop" in text
    assert "do not enable recovery" in text
    assert "do not mutate runtime state" in text
    assert "py -m pytest tests/test_runtime_launch_contract.py -q" in text
    assert "do not run full suite, nightly, regression, or long validation" in text
