import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_queue_admission.py"
DOC = ROOT / "docs/runtime_activation_queue_admission.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_queue_admission_imports_and_public_api_exists():
    from core.runtime import runtime_activation_queue_admission

    assert hasattr(
        runtime_activation_queue_admission,
        "preview_runtime_activation_queue_admission",
    )
    assert runtime_activation_queue_admission.__all__ == [
        "preview_runtime_activation_queue_admission"
    ]


def test_queue_admission_preview_is_deterministic():
    from core.runtime.runtime_activation_queue_admission import (
        preview_runtime_activation_queue_admission,
    )

    preview = {
        "task_id": "task-1",
        "task_type": "dry",
        "lineage_id": "lineage-1",
        "trace_id": "trace-1",
    }

    first = preview_runtime_activation_queue_admission(preview)
    second = preview_runtime_activation_queue_admission(preview)

    assert first == second
    assert first["mode"] == "queue_admission_preview"
    assert first["queue_status"] == "disabled"
    assert first["admission_reason"] == "queue_insertion_disabled"
    assert first["result"] == "blocked"


def test_queue_admission_insertion_and_runtime_mutation_are_disabled():
    from core.runtime.runtime_activation_queue_admission import (
        preview_runtime_activation_queue_admission,
    )

    result = preview_runtime_activation_queue_admission({})

    assert result["queue_admission_ready"] is True
    assert result["queue_insert_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["task_created"] is False
    assert result["queue_file_written"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_queue_admission_has_no_downstream_calls_or_tool_execution():
    from core.runtime.runtime_activation_queue_admission import (
        preview_runtime_activation_queue_admission,
    )

    result = preview_runtime_activation_queue_admission({})

    assert result["scheduler_called"] is False
    assert result["executor_called"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_loop_started"] is False


def test_queue_admission_snapshots_identity_and_lineage_without_mutating_input():
    from core.runtime.runtime_activation_queue_admission import (
        preview_runtime_activation_queue_admission,
    )

    preview = {
        "task_id": "task-1",
        "task_name": "Preview",
        "lineage_id": "lineage-1",
        "parent_id": "parent-1",
        "unrelated": {"nested": True},
    }
    original = {
        "task_id": "task-1",
        "task_name": "Preview",
        "lineage_id": "lineage-1",
        "parent_id": "parent-1",
        "unrelated": {"nested": True},
    }

    result = preview_runtime_activation_queue_admission(preview)

    assert preview == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == [
        "lineage_id",
        "parent_id",
        "task_id",
        "task_name",
        "unrelated",
    ]
    assert result["task_identity"] == {
        "task_id": "task-1",
        "task_name": "Preview",
    }
    assert result["lineage"] == {
        "lineage_id": "lineage-1",
        "parent_id": "parent-1",
    }


def test_queue_admission_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_queue_admission import (
        preview_runtime_activation_queue_admission,
    )

    none_result = preview_runtime_activation_queue_admission(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["queue_insert_allowed"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_queue_admission(malformed)
        assert result["queue_status"] == "disabled"
        assert result["queue_insert_allowed"] is False
        assert result["runtime_mutation_allowed"] is False


def test_no_queue_io_subprocess_scheduler_or_executor_dependency():
    source = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.append(node.module or "")

    assert not any("task_queue" in module.lower() for module in imported_modules)
    assert not any("work_package_queue" in module.lower() for module in imported_modules)
    assert not any("runtime_queue" in module.lower() for module in imported_modules)
    assert not any("scheduler" in module.lower() for module in imported_modules)
    assert not any("executor" in module.lower() for module in imported_modules)
    assert not any("subprocess" in module.lower() for module in imported_modules)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in {"open", "Path"}
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr != "write"


def test_docs_contain_preview_and_future_insertion_boundaries():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "Queue insertion remains a future package",
        "Queue file writes are forbidden",
        "Runtime task creation is forbidden",
        "Scheduler calls are forbidden",
        "Executor calls are forbidden",
        "Tool execution is forbidden",
        "Runtime mutation is forbidden",
        "Repo/file mutation is forbidden",
    ):
        assert phrase in text


def test_package_sequence_records_849_856():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 849-856" in text
    assert "Runtime Queue Admission Bridge (Disabled)" in text
