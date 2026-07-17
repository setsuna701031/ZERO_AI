from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_executor_noop_admission.py"
DOC = ROOT / "docs/runtime_activation_executor_noop_admission.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"

REQUIRED_BYPASS_PREVENTION = {
    "no_real_executor_call",
    "no_tool_execution",
    "no_mutation",
    "no_activation_enablement",
}

REQUIRED_DOC_PHRASES = (
    "executor no-op admission only",
    "no real executor call",
    "no tool execution",
    "no activation enablement",
    "no mutation",
    "no scheduler execution",
)


def test_runtime_activation_executor_noop_admission_imports_and_public_api_exists():
    from core.runtime import runtime_activation_executor_noop_admission

    assert hasattr(
        runtime_activation_executor_noop_admission,
        "prepare_runtime_activation_executor_noop_admission",
    )
    assert runtime_activation_executor_noop_admission.__all__ == [
        "prepare_runtime_activation_executor_noop_admission"
    ]


def test_executor_noop_admission_returns_blocked_noop_result_and_checks_scheduler_layer():
    from core.runtime.runtime_activation_executor_noop_admission import (
        prepare_runtime_activation_executor_noop_admission,
    )

    result = prepare_runtime_activation_executor_noop_admission(None)

    assert result["enabled"] is False
    assert result["mode"] == "executor_noop_admission"
    assert result["execution_result"] == "blocked"
    assert result["reason"] == "executor_admission_disabled"
    assert result["scheduler_dry_dispatch_checked"] is True
    assert result["scheduler_dry_dispatch_result"]["mode"] == "scheduler_dry_dispatch"
    assert result["scheduler_dry_dispatch_result"]["dispatch_result"] == "blocked"


def test_executor_noop_admission_keeps_activation_execution_and_mutation_disabled():
    from core.runtime.runtime_activation_executor_noop_admission import (
        prepare_runtime_activation_executor_noop_admission,
    )

    result = prepare_runtime_activation_executor_noop_admission({})

    assert result["activation_enabled"] is False
    assert result["executor_admission_checked"] is True
    assert result["executor_admitted"] is False
    assert result["executor_called"] is False
    assert result["executor_noop"] is True
    assert result["tool_execution_allowed"] is False
    assert result["mutation_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_mutated"] is False


def test_malformed_request_safe_and_dict_input_unchanged():
    from core.runtime.runtime_activation_executor_noop_admission import (
        prepare_runtime_activation_executor_noop_admission,
    )

    request = {"activation": "dry", "nested": {"value": 1}}
    original = {"activation": "dry", "nested": {"value": 1}}
    result = prepare_runtime_activation_executor_noop_admission(request)

    assert request == original
    assert result["request_present"] is True
    assert result["request_type"] == "dict"

    for malformed in ("bad", 7, ["not", "a", "dict"], object()):
        malformed_result = prepare_runtime_activation_executor_noop_admission(
            malformed
        )
        assert malformed_result["execution_result"] == "blocked"
        assert malformed_result["activation_enabled"] is False
        assert malformed_result["executor_admitted"] is False
        assert malformed_result["executor_called"] is False
        assert malformed_result["tool_execution_allowed"] is False
        assert malformed_result["mutation_allowed"] is False


def test_bypass_prevention_contains_required_entries_and_is_copy_safe():
    from core.runtime.runtime_activation_executor_noop_admission import (
        prepare_runtime_activation_executor_noop_admission,
    )

    first = prepare_runtime_activation_executor_noop_admission({})
    second = prepare_runtime_activation_executor_noop_admission({})

    assert REQUIRED_BYPASS_PREVENTION.issubset(first["bypass_prevention"])
    assert first["bypass_prevention"] is not second["bypass_prevention"]
    assert (
        first["scheduler_dry_dispatch_result"]
        is not second["scheduler_dry_dispatch_result"]
    )
    assert (
        first["scheduler_dry_dispatch_result"]["bypass_prevention"]
        is not second["scheduler_dry_dispatch_result"]["bypass_prevention"]
    )


def test_no_executor_import_dependency():
    source = MODULE.read_text(encoding="utf-8")
    import_lines = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]

    assert not any("executor" in line.lower() for line in import_lines)
    assert not any("tool" in line.lower() for line in import_lines)


def test_docs_contain_guard_phrases():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")
    for phrase in REQUIRED_DOC_PHRASES:
        assert phrase in text


def test_package_sequence_records_825_832():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 825-832" in text
    assert "Runtime Activation Executor No-op Admission Bridge" in text
