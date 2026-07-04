from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/runtime_activation_task_intake.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_runtime_activation_task_intake_imports_and_public_api_exists():
    from core.runtime import runtime_activation_task_intake

    assert hasattr(
        runtime_activation_task_intake,
        "prepare_runtime_activation_task_intake",
    )
    assert runtime_activation_task_intake.__all__ == [
        "prepare_runtime_activation_task_intake"
    ]


def test_task_intake_accepts_none_and_returns_blocked_result():
    from core.runtime.runtime_activation_task_intake import (
        prepare_runtime_activation_task_intake,
    )

    result = prepare_runtime_activation_task_intake(None)

    assert result["enabled"] is False
    assert result["mode"] == "task_intake_preflight"
    assert result["result"] == "blocked"
    assert result["reason"] == "activation_not_enabled"
    assert result["intent_present"] is False
    assert result["intent_type"] == "NoneType"


def test_task_intake_accepts_dict_does_not_mutate_and_calls_noop_admission_path():
    from core.runtime.runtime_activation_task_intake import (
        prepare_runtime_activation_task_intake,
    )

    intent = {"task": "summarize", "metadata": {"priority": "low"}}
    original = {"task": "summarize", "metadata": {"priority": "low"}}

    result = prepare_runtime_activation_task_intake(intent)

    assert intent == original
    assert result["intent_present"] is True
    assert result["intent_type"] == "dict"
    assert result["activation_forwarded"] is True
    assert result["downstream_activation_result"]["mode"] == "executor_noop_admission"
    assert result["downstream_activation_result"]["execution_result"] == "blocked"
    assert (
        result["downstream_activation_result"]["reason"]
        == "executor_admission_disabled"
    )


def test_task_intake_malformed_input_safe():
    from core.runtime.runtime_activation_task_intake import (
        prepare_runtime_activation_task_intake,
    )

    for malformed in ("bad", 7, ["not", "a", "dict"], object()):
        result = prepare_runtime_activation_task_intake(malformed)
        assert result["result"] == "blocked"
        assert result["task_created"] is False
        assert result["task_scheduled"] is False
        assert result["task_executed"] is False
        assert result["executor_called"] is False
        assert result["mutation_allowed"] is False
        assert result["runtime_state_mutated"] is False


def test_task_intake_keeps_task_scheduler_executor_tools_and_mutation_disabled():
    from core.runtime.runtime_activation_task_intake import (
        prepare_runtime_activation_task_intake,
    )

    result = prepare_runtime_activation_task_intake({})

    assert result["task_intake_checked"] is True
    assert result["task_created"] is False
    assert result["task_scheduled"] is False
    assert result["task_executed"] is False
    assert result["scheduler_called"] is False
    assert result["executor_called"] is False
    assert result["tool_execution_allowed"] is False
    assert result["mutation_allowed"] is False
    assert result["runtime_state_mutated"] is False


def test_task_intake_downstream_result_is_copy_safe():
    from core.runtime.runtime_activation_task_intake import (
        prepare_runtime_activation_task_intake,
    )

    first = prepare_runtime_activation_task_intake({})
    second = prepare_runtime_activation_task_intake({})

    assert (
        first["downstream_activation_result"]
        is not second["downstream_activation_result"]
    )
    assert (
        first["downstream_activation_result"]["bypass_prevention"]
        is not second["downstream_activation_result"]["bypass_prevention"]
    )


def test_docs_contain_guard_phrases():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")
    for phrase in (
        "first task-facing activation layer",
        "executor noop admission path",
        "no task execution",
        "no scheduler call",
        "no executor call",
        "no tool execution",
        "no mutation",
        "no runtime state mutation",
    ):
        assert phrase in text


def test_package_sequence_records_833_840():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 833-840" in text
    assert "Runtime Activation Task Intent Intake" in text
