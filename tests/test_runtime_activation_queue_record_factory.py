import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_queue_record_factory.py"
DOC = ROOT / "docs/runtime_activation_queue_record_factory.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_queue_record_factory_imports_and_public_api_exists():
    from core.runtime import runtime_activation_queue_record_factory

    assert hasattr(
        runtime_activation_queue_record_factory,
        "preview_runtime_activation_queue_record_factory",
    )
    assert runtime_activation_queue_record_factory.__all__ == [
        "preview_runtime_activation_queue_record_factory"
    ]


def test_queue_record_factory_preview_is_deterministic():
    from core.runtime.runtime_activation_queue_record_factory import (
        preview_runtime_activation_queue_record_factory,
    )

    writer = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
        "future_queue_record_preview": {"record_type": "runtime_queue_task"},
    }

    first = preview_runtime_activation_queue_record_factory(writer)
    second = preview_runtime_activation_queue_record_factory(writer)

    assert first == second
    assert first["mode"] == "queue_record_factory_preview"
    assert first["record_status"] == "disabled"
    assert first["record_reason"] == "queue_record_factory_disabled"
    assert first["result"] == "blocked"


def test_queue_record_factory_does_not_create_persist_execute_or_mutate():
    from core.runtime.runtime_activation_queue_record_factory import (
        preview_runtime_activation_queue_record_factory,
    )

    result = preview_runtime_activation_queue_record_factory({})

    assert result["record_factory_ready"] is True
    assert result["queue_record_created"] is False
    assert result["queue_record_persisted"] is False
    assert result["queue_record_execution_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["queue_insert_allowed"] is False
    assert result["file_write_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_queue_record_factory_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_queue_record_factory import (
        preview_runtime_activation_queue_record_factory,
    )

    result = preview_runtime_activation_queue_record_factory({})

    assert result["scheduler_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False


def test_queue_record_factory_preserves_identity_lineage_and_builds_preview_record():
    from core.runtime.runtime_activation_queue_record_factory import (
        preview_runtime_activation_queue_record_factory,
    )

    writer = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "future_queue_record_preview": {
            "record_status": "future_package",
            "record_type": "runtime_queue_task",
        },
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "future_queue_record_preview": {
            "record_status": "future_package",
            "record_type": "runtime_queue_task",
        },
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_queue_record_factory(writer)

    assert writer == original
    assert result["identity_snapshot"] == {
        "task_id": "task-1",
        "task_name": "Preview",
    }
    assert result["lineage_snapshot"] == {
        "lineage_id": "lineage-1",
        "trace_id": "trace-1",
    }
    assert result["queue_record_preview"] == {
        "record_kind": "runtime_queue_task",
        "record_version": 1,
        "record_status": "preview_only",
        "identity": {"task_id": "task-1", "task_name": "Preview"},
        "lineage": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
        "writer_record_preview": {
            "record_status": "future_package",
            "record_type": "runtime_queue_task",
        },
        "persist_enabled": False,
        "execution_enabled": False,
    }


def test_queue_record_factory_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_queue_record_factory import (
        preview_runtime_activation_queue_record_factory,
    )

    none_result = preview_runtime_activation_queue_record_factory(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["queue_record_created"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_queue_record_factory(malformed)
        assert result["queue_record_created"] is False
        assert result["queue_record_persisted"] is False
        assert result["queue_record_execution_allowed"] is False
        assert result["runtime_mutation_allowed"] is False


def test_ast_has_no_downstream_imports_or_forbidden_calls():
    source = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = []
    forbidden_calls = {
        "open",
        "Path",
        "Popen",
        "run",
        "call",
        "check_call",
        "check_output",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.append(node.module or "")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"write", "run", "call", "start"}

    assert not any("queue" in module.lower() for module in imported_modules)
    assert not any("storage" in module.lower() for module in imported_modules)
    assert not any("scheduler" in module.lower() for module in imported_modules)
    assert not any("executor" in module.lower() for module in imported_modules)
    assert not any("subprocess" in module.lower() for module in imported_modules)
    assert not any("tool" in module.lower() for module in imported_modules)


def test_docs_explain_disabled_record_factory_boundary():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "must not persist records",
        "Queue insert is forbidden",
        "File write is forbidden",
        "Queue storage imports are forbidden",
        "Scheduler imports and calls are forbidden",
        "Executor imports and calls are forbidden",
        "Tool execution is forbidden",
        "Queue record persistence is forbidden",
        "GO only for disabled queue record factory preview",
    ):
        assert phrase in text


def test_package_sequence_records_881_888():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 881-888" in text
    assert "Runtime Queue Record Factory Preview (Disabled)" in text
