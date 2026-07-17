from pathlib import Path


DOC = Path("docs/runtime_recovery_hook_readiness.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_158_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 158")
    end = text.find("## Package 159", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_hook_readiness_doc_exists():
    assert DOC.exists()


def test_hook_readiness_required_sections_exist():
    text = _text(DOC)
    for section in (
        "## Purpose",
        "## Scheduler Readiness Rules",
        "## Operator Readiness Rules",
        "## Runtime Supervisor Readiness Rules",
        "## Native Runtime Readiness Rules",
        "## Required Activation Report",
        "## Required References",
        "## Forbidden Direct Hooks",
        "## GO / NO-GO",
        "## Next Package",
    ):
        assert section in text


def test_scheduler_operator_supervisor_and_native_rules_exist():
    text = _text(DOC)
    for phrase in (
        "Scheduler-owned contract",
        "Scheduler admission semantics",
        "Operator-owned contract",
        "Operator decision semantics",
        "Runtime Supervisor-owned contract",
        "supervision semantics",
        "Native Runtime-owned contract",
        "native execution semantics",
    ):
        assert phrase in text


def test_required_activation_report_is_documented():
    text = _text(DOC)
    assert "aer.runtime.recovery.activation_response.v1" in text
    for phrase in (
        "`activation_state` is `prepared`",
        "`prepared` is `true`",
        "`blocked` is `false`",
        "`denied` is `false`",
        "`activation_only` is `true`",
        "`executes_recovery` is `false`",
        "`side_effects_performed` is `false`",
    ):
        assert phrase in text


def test_required_references_are_documented():
    text = _text(DOC)
    for reference in (
        "authority reference: `aer.runtime.recovery.execution_authority_response.v1`",
        "intent reference: `aer.runtime.recovery.execution_intent_response.v1`",
        "bridge reference: `aer.runtime.recovery.runtime_bridge_response.v1`",
        "executor report reference: `aer.runtime.recovery.executor_report.v1`",
        "runtime integration report reference: `aer.runtime.recovery.runtime_integration_report.v1`",
    ):
        assert reference in text


def test_forbidden_direct_hooks_are_documented():
    text = _text(DOC)
    for hook in (
        "Scheduler admission paths",
        "Scheduler scheduling paths",
        "Dispatcher command paths",
        "Operator runtime action paths",
        "Runtime Supervisor paths",
        "Native Runtime execution paths",
        "persistence write paths",
        "replay action paths",
        "audit emission paths",
        "journal emission paths",
        "subprocess paths",
        "file IO paths",
        "runtime mutation paths",
    ):
        assert hook in text


def test_go_no_go_and_sequence_entry_exist():
    text = _text(DOC)
    assert "Final decision: GO" in text
    assert "Next package: Package 159" in text

    entry = _package_158_entry()
    assert "## Package 158" in entry
    assert "Recovery Runtime Hook Readiness Seal" in entry
    assert "docs/runtime_recovery_hook_readiness.md" in entry
    assert "tests/test_runtime_recovery_hook_readiness.py" in entry
    assert "python -m pytest tests/test_runtime_recovery_hook_readiness.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 159" in entry


def test_hook_readiness_doc_has_no_implementation_tokens():
    text = _text(DOC)
    for token in (
        "def ",
        "class ",
        "import ",
        "scheduler.schedule(",
        "dispatcher.dispatch(",
        "operator.apply(",
        "subprocess.",
        "open(",
        ".write(",
        "Path(",
    ):
        assert token not in text
