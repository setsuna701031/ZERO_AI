from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_runtime_hook_wiring_v1.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 163")
    end = text.find("## Package 164", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_runtime_hook_wiring_contract_exists():
    assert CONTRACT.exists()


def test_runtime_hook_wiring_contract_required_sections_exist():
    text = _text(CONTRACT)
    for section in (
        "## Purpose",
        "## Wiring Surfaces",
        "## Required References",
        "## Declarative Wiring Rules",
        "## Package 159-162 Boundary Preservation",
        "## Gate Requirement",
        "## Prohibited Runtime Hooks",
        "## Compatibility Policy",
        "## GO / NO-GO",
        "## Next Package",
    ):
        assert section in text


def test_runtime_hook_wiring_contract_requires_passive_adapter_surfaces():
    text = _text(CONTRACT)
    for contract in (
        "aer.runtime.recovery.scheduler_adapter_report.v1",
        "aer.runtime.recovery.operator_adapter_report.v1",
        "aer.runtime.recovery.supervisor_adapter_report.v1",
        "aer.runtime.recovery.native_adapter_report.v1",
    ):
        assert contract in text
    assert "Runtime Permission" in text
    assert "None" in text


def test_runtime_hook_wiring_contract_preserves_required_references_and_boundaries():
    text = _text(CONTRACT)
    for phrase in (
        "activation reference",
        "authority reference",
        "intent reference",
        "bridge reference",
        "executor report reference",
        "Package 159 Scheduler Passive Adapter remains adapter-only",
        "Package 160 Operator Passive Adapter remains adapter-only",
        "Package 161 Runtime Supervisor Passive Adapter remains adapter-only",
        "Package 162 Native Runtime Passive Adapter remains adapter-only",
        "No hook wiring contract may reinterpret a prepared adapter report as runtime execution permission",
    ):
        assert phrase in text


def test_runtime_hook_wiring_contract_keeps_gate_off_and_forbids_runtime_hooks():
    text = _text(CONTRACT)
    assert "The gate must be OFF by default" in text
    for phrase in (
        "activate Recovery",
        "create Scheduler admissions",
        "request Operator actions",
        "dispatch commands",
        "supervise runtime sessions",
        "call Native Runtime execution",
        "mutate runtime state",
        "Scheduler scheduling paths",
        "Operator runtime paths",
        "Dispatcher command paths",
        "Runtime Supervisor paths",
        "Native Runtime paths",
    ):
        assert phrase in text


def test_runtime_hook_wiring_contract_go_no_go_and_sequence_entry():
    text = _text(CONTRACT)
    assert "Final decision: GO" in text
    assert "Next package: Package 164" in text

    entry = _package_entry()
    assert "## Package 163" in entry
    assert "Runtime Hook Wiring Contract" in entry
    assert "docs/contracts/runtime/recovery_runtime_hook_wiring_v1.md" in entry
    assert "tests/test_runtime_recovery_hook_wiring_contract.py" in entry
    assert "python -m pytest tests/test_runtime_recovery_hook_wiring_contract.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 164" in entry


def test_runtime_hook_wiring_contract_has_no_implementation_tokens():
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
