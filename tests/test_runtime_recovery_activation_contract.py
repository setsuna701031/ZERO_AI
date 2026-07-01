from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_activation_v1.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_156_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 156")
    end = text.find("## Package 157", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_activation_contract_exists():
    assert CONTRACT.exists()


def test_required_sections_exist():
    text = _text(CONTRACT)
    for section in (
        "## Purpose",
        "## Activation Request Schema",
        "## Activation Response Schema",
        "## Required Authority Reference",
        "## Required Intent Reference",
        "## Required Bridge Reference",
        "## Required Executor Report Reference",
        "## Allowed Activation States",
        "## Forbidden Activation States",
        "## Activation Boundary Rules",
        "## Prohibited Direct Runtime Hooks",
        "## Compatibility Policy",
        "## GO / NO-GO",
        "## Next Package",
    ):
        assert section in text


def test_activation_request_schema_exists():
    text = _text(CONTRACT)
    assert "aer.runtime.recovery.activation_request.v1" in text
    for field in (
        "`activation_id`",
        "`requested_state`",
        "`integration_report_reference`",
        "`authority_reference`",
        "`intent_reference`",
        "`bridge_reference`",
        "`executor_report_reference`",
        "`metadata`",
        "`activation_only`",
    ):
        assert field in text


def test_activation_response_schema_exists():
    text = _text(CONTRACT)
    assert "aer.runtime.recovery.activation_response.v1" in text
    for field in (
        "`prepared`",
        "`blocked`",
        "`denied`",
        "`activation_state`",
        "`denied_runtime_hooks`",
        "`executes_recovery`",
        "`side_effects_performed`",
        "`plain_dict_only`",
    ):
        assert field in text
    assert "Activation response preparation does not authorize runtime execution" in text


def test_required_references_exist():
    text = _text(CONTRACT)
    assert "aer.runtime.recovery.execution_authority_response.v1" in text
    assert "aer.runtime.recovery.execution_intent_response.v1" in text
    assert "aer.runtime.recovery.runtime_bridge_response.v1" in text
    assert "aer.runtime.recovery.executor_report.v1" in text
    assert "`authorized_for_future_handoff`" in text
    assert "`prepared_no_side_effects`" in text


def test_allowed_and_forbidden_activation_states_exist():
    text = _text(CONTRACT)
    for allowed in ("`prepared`", "`blocked`", "`denied`"):
        assert allowed in text
    for forbidden in (
        "`activated`",
        "`running`",
        "`scheduled`",
        "`dispatched`",
        "`operator_started`",
        "`executed`",
        "`persisted`",
        "`replayed`",
        "`audited`",
        "`journaled`",
        "`mutated`",
    ):
        assert forbidden in text


def test_boundary_rules_and_prohibited_hooks_exist():
    text = _text(CONTRACT)
    for phrase in (
        "Activation may validate authority, intent, bridge, and executor report references",
        "Activation must not create Scheduler admissions",
        "Activation must not dispatch runtime commands",
        "Activation must not request or apply Operator actions",
        "Activation must not supervise runtime sessions",
        "Activation must not call Native Runtime execution",
        "Scheduler admission or scheduling paths",
        "Dispatcher command paths",
        "Operator runtime action paths",
        "Runtime Supervisor paths",
        "Native Runtime execution paths",
    ):
        assert phrase in text


def test_compatibility_go_no_go_and_sequence_entry_exist():
    text = _text(CONTRACT)
    assert "Runtime Recovery Activation v1 is compatible only with passive Package 152 integration reports" in text
    assert "Final decision: GO" in text
    assert "Next package: Package 157" in text

    entry = _package_156_entry()
    assert "## Package 156" in entry
    assert "Recovery Runtime Activation Contract" in entry
    assert "docs/contracts/runtime/recovery_activation_v1.md" in entry
    assert "tests/test_runtime_recovery_activation_contract.py" in entry
    assert "python -m pytest tests/test_runtime_recovery_activation_contract.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 157" in entry
