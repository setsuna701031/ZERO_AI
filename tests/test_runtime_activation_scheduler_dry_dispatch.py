from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_scheduler_dry_dispatch.py"
DOC = ROOT / "docs/runtime_activation_scheduler_dry_dispatch.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"

REQUIRED_BYPASS_PREVENTION = {
    "no_scheduler_execution",
    "no_executor_call",
    "no_mutation",
    "no_activation_enablement",
}

REQUIRED_DOC_PHRASES = (
    "dry dispatch bridge only",
    "scheduler ownership check only",
    "no scheduler execution",
    "no executor execution",
    "no activation enablement",
    "no mutation",
)


def test_runtime_activation_scheduler_dry_dispatch_imports_and_public_api_exists():
    from core.runtime import runtime_activation_scheduler_dry_dispatch

    assert hasattr(
        runtime_activation_scheduler_dry_dispatch,
        "prepare_runtime_activation_scheduler_dry_dispatch",
    )
    assert runtime_activation_scheduler_dry_dispatch.__all__ == [
        "prepare_runtime_activation_scheduler_dry_dispatch"
    ]


def test_scheduler_dry_dispatch_returns_blocked_result_and_checks_dry_wiring():
    from core.runtime.runtime_activation_scheduler_dry_dispatch import (
        prepare_runtime_activation_scheduler_dry_dispatch,
    )

    result = prepare_runtime_activation_scheduler_dry_dispatch(None)

    assert result["enabled"] is False
    assert result["mode"] == "scheduler_dry_dispatch"
    assert result["dispatch_result"] == "blocked"
    assert result["reason"] == "scheduler_dispatch_disabled"
    assert result["dry_wiring_checked"] is True
    assert result["dry_wiring_result"]["mode"] == "dry_wiring"
    assert result["dry_wiring_result"]["result"] == "blocked"
    assert result["dry_wiring_result"]["reason"] == "activation_disabled"


def test_scheduler_dry_dispatch_keeps_all_execution_and_mutation_disabled():
    from core.runtime.runtime_activation_scheduler_dry_dispatch import (
        prepare_runtime_activation_scheduler_dry_dispatch,
    )

    result = prepare_runtime_activation_scheduler_dry_dispatch({})

    assert result["activation_enabled"] is False
    assert result["scheduler_admission_checked"] is True
    assert result["scheduler_dispatch_allowed"] is False
    assert result["scheduler_executed"] is False
    assert result["executor_allowed"] is False
    assert result["executor_called"] is False
    assert result["mutation_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_mutated"] is False


def test_malformed_request_safe_and_dict_input_unchanged():
    from core.runtime.runtime_activation_scheduler_dry_dispatch import (
        prepare_runtime_activation_scheduler_dry_dispatch,
    )

    request = {"activation": "dry", "nested": {"value": 1}}
    original = {"activation": "dry", "nested": {"value": 1}}
    result = prepare_runtime_activation_scheduler_dry_dispatch(request)

    assert request == original
    assert result["request_present"] is True
    assert result["request_type"] == "dict"

    for malformed in ("bad", 7, ["not", "a", "dict"], object()):
        malformed_result = prepare_runtime_activation_scheduler_dry_dispatch(
            malformed
        )
        assert malformed_result["dispatch_result"] == "blocked"
        assert malformed_result["activation_enabled"] is False
        assert malformed_result["scheduler_dispatch_allowed"] is False
        assert malformed_result["executor_called"] is False
        assert malformed_result["mutation_allowed"] is False


def test_bypass_prevention_contains_required_entries_and_is_copy_safe():
    from core.runtime.runtime_activation_scheduler_dry_dispatch import (
        prepare_runtime_activation_scheduler_dry_dispatch,
    )

    first = prepare_runtime_activation_scheduler_dry_dispatch({})
    second = prepare_runtime_activation_scheduler_dry_dispatch({})

    assert REQUIRED_BYPASS_PREVENTION.issubset(first["bypass_prevention"])
    assert first["bypass_prevention"] is not second["bypass_prevention"]
    assert first["dry_wiring_result"] is not second["dry_wiring_result"]
    assert (
        first["dry_wiring_result"]["bypass_prevention"]
        is not second["dry_wiring_result"]["bypass_prevention"]
    )


def test_no_scheduler_or_executor_import_dependency():
    source = MODULE.read_text(encoding="utf-8")
    import_lines = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]

    assert not any("scheduler" in line.lower() for line in import_lines)
    assert not any("executor" in line.lower() for line in import_lines)
    assert not any("run_one_step" in line for line in import_lines)


def test_docs_contain_guard_phrases():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")
    for phrase in REQUIRED_DOC_PHRASES:
        assert phrase in text


def test_package_sequence_records_817_824():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 817-824" in text
    assert "Runtime Activation Scheduler Dry Dispatch Bridge" in text
