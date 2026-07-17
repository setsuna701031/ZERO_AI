from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/runtime_activation_first_dry_wiring.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"

REQUIRED_BYPASS_PREVENTION = {
    "no_scheduler_dispatch",
    "no_executor_call",
    "no_mutation",
    "no_activation_enablement",
}

REQUIRED_DOC_PHRASES = (
    "first dry wiring only",
    "no real activation",
    "no scheduler dispatch",
    "no executor call",
    "no mutation",
    "dry wiring is blocked by default",
    "activation remains disabled",
)


def test_runtime_activation_dry_wiring_module_imports_and_public_function_exists():
    from core.runtime import runtime_activation_dry_wiring

    assert hasattr(runtime_activation_dry_wiring, "prepare_runtime_activation_dry_wiring")
    assert runtime_activation_dry_wiring.__all__ == ["prepare_runtime_activation_dry_wiring"]


def test_none_request_returns_blocked_disabled_result():
    from core.runtime.runtime_activation_dry_wiring import (
        prepare_runtime_activation_dry_wiring,
    )

    result = prepare_runtime_activation_dry_wiring(None)

    assert result["enabled"] is False
    assert result["mode"] == "dry_wiring"
    assert result["activation_enabled"] is False
    assert result["dispatch_allowed"] is False
    assert result["executor_allowed"] is False
    assert result["mutation_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_mutated"] is False
    assert result["result"] == "blocked"
    assert result["reason"] == "activation_disabled"
    assert result["request_present"] is False
    assert result["request_type"] == "NoneType"


def test_dict_request_is_not_mutated_and_checks_are_true():
    from core.runtime.runtime_activation_dry_wiring import (
        prepare_runtime_activation_dry_wiring,
    )

    request = {"activation": "requested", "nested": {"value": 1}}
    original = {"activation": "requested", "nested": {"value": 1}}

    result = prepare_runtime_activation_dry_wiring(request)

    assert request == original
    assert result["request_present"] is True
    assert result["request_type"] == "dict"
    assert result["adapter_contract_checked"] is True
    assert result["adapter_admission_checked"] is True
    assert result["adapter_authorization_checked"] is True
    assert result["adapter_lifecycle_checked"] is True
    assert result["adapter_dry_run_checked"] is True


def test_malformed_request_does_not_raise_and_remains_blocked():
    from core.runtime.runtime_activation_dry_wiring import (
        prepare_runtime_activation_dry_wiring,
    )

    for malformed in ("bad", 7, ["not", "a", "dict"], object()):
        result = prepare_runtime_activation_dry_wiring(malformed)
        assert result["result"] == "blocked"
        assert result["activation_enabled"] is False
        assert result["dispatch_allowed"] is False
        assert result["executor_allowed"] is False
        assert result["mutation_allowed"] is False
        assert result["runtime_state_mutated"] is False
        assert result["repo_mutated"] is False


def test_bypass_prevention_contains_required_entries_and_is_copy_safe():
    from core.runtime.runtime_activation_dry_wiring import (
        prepare_runtime_activation_dry_wiring,
    )

    first = prepare_runtime_activation_dry_wiring({})
    second = prepare_runtime_activation_dry_wiring({})

    assert REQUIRED_BYPASS_PREVENTION.issubset(first["bypass_prevention"])
    assert first["bypass_prevention"] is not second["bypass_prevention"]

    first["bypass_prevention"].append("local_change")
    assert "local_change" not in second["bypass_prevention"]


def test_docs_contain_required_guard_phrases():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")
    for phrase in REQUIRED_DOC_PHRASES:
        assert phrase in text


def test_package_sequence_records_809_816():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 809-816" in text
    assert "Runtime Activation First Dry Wiring" in text
