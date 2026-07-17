from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/runtime_activation_task_materialization.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_task_materialization_imports_and_public_api_exists():
    from core.runtime import runtime_activation_task_materialization

    assert hasattr(
        runtime_activation_task_materialization,
        "preview_runtime_activation_task_materialization",
    )
    assert runtime_activation_task_materialization.__all__ == [
        "preview_runtime_activation_task_materialization"
    ]


def test_task_materialization_preview_is_deterministic_and_disabled():
    from core.runtime.runtime_activation_task_materialization import (
        preview_runtime_activation_task_materialization,
    )

    intake = {"z": 1, "a": {"nested": True}}

    first = preview_runtime_activation_task_materialization(intake)
    second = preview_runtime_activation_task_materialization(intake)

    assert first == second
    assert first["enabled"] is False
    assert first["mode"] == "task_materialization_preview"
    assert first["materialization_status"] == "disabled"
    assert first["result"] == "blocked"
    assert first["reason"] == "task_materialization_disabled"


def test_task_materialization_preview_keeps_all_effects_disabled():
    from core.runtime.runtime_activation_task_materialization import (
        preview_runtime_activation_task_materialization,
    )

    result = preview_runtime_activation_task_materialization({})

    assert result["task_created"] is False
    assert result["queue_write_allowed"] is False
    assert result["scheduler_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False
    assert result["preview_only"] is True


def test_task_materialization_preview_does_not_mutate_input():
    from core.runtime.runtime_activation_task_materialization import (
        preview_runtime_activation_task_materialization,
    )

    intake = {"task": "preview", "metadata": {"priority": "low"}}
    original = {"task": "preview", "metadata": {"priority": "low"}}

    result = preview_runtime_activation_task_materialization(intake)

    assert intake == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == ["metadata", "task"]


def test_task_materialization_preview_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_task_materialization import (
        preview_runtime_activation_task_materialization,
    )

    none_result = preview_runtime_activation_task_materialization(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_task_materialization(malformed)
        assert result["materialization_status"] == "disabled"
        assert result["task_created"] is False
        assert result["queue_write_allowed"] is False
        assert result["runtime_state_mutated"] is False
        assert result["repo_state_mutated"] is False


def test_no_public_execution_api_exists():
    from core.runtime import runtime_activation_task_materialization

    public_names = set(runtime_activation_task_materialization.__all__)

    assert public_names == {"preview_runtime_activation_task_materialization"}
    assert not hasattr(runtime_activation_task_materialization, "materialize_task")
    assert not hasattr(runtime_activation_task_materialization, "create_task")
    assert not hasattr(runtime_activation_task_materialization, "execute_task")
    assert not hasattr(runtime_activation_task_materialization, "enqueue_task")


def test_docs_contain_no_go_boundaries_and_issue_reporting_rule():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "Task creation is forbidden",
        "Queue write is forbidden",
        "Scheduler call is forbidden",
        "Executor call is forbidden",
        "Tool call is forbidden",
        "Runtime mutation is forbidden",
        "Repo mutation is forbidden",
        "File mutation is forbidden",
        "non-mainline issue",
        "GO only for disabled task materialization preview",
    ):
        assert phrase in text


def test_package_sequence_records_841_848():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 841-848" in text
    assert "disabled Task Materialization Readiness" in text
