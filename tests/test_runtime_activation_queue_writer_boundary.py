import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_queue_writer_boundary.py"
DOC = ROOT / "docs/runtime_activation_queue_writer_boundary.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_queue_writer_boundary_imports_and_public_api_exists():
    from core.runtime import runtime_activation_queue_writer_boundary

    assert hasattr(
        runtime_activation_queue_writer_boundary,
        "preview_runtime_activation_queue_writer_boundary",
    )
    assert runtime_activation_queue_writer_boundary.__all__ == [
        "preview_runtime_activation_queue_writer_boundary"
    ]


def test_queue_writer_boundary_preview_is_deterministic():
    from core.runtime.runtime_activation_queue_writer_boundary import (
        preview_runtime_activation_queue_writer_boundary,
    )

    persistence = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
    }

    first = preview_runtime_activation_queue_writer_boundary(persistence)
    second = preview_runtime_activation_queue_writer_boundary(persistence)

    assert first == second
    assert first["mode"] == "queue_writer_boundary_preview"
    assert first["writer_status"] == "disabled"
    assert first["writer_reason"] == "queue_writer_disabled"
    assert first["result"] == "blocked"


def test_queue_writer_boundary_keeps_writer_and_mutation_disabled():
    from core.runtime.runtime_activation_queue_writer_boundary import (
        preview_runtime_activation_queue_writer_boundary,
    )

    result = preview_runtime_activation_queue_writer_boundary({})

    assert result["writer_boundary_ready"] is True
    assert result["queue_writer_available"] is False
    assert result["queue_record_write_allowed"] is False
    assert result["queue_file_write_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_queue_writer_boundary_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_queue_writer_boundary import (
        preview_runtime_activation_queue_writer_boundary,
    )

    result = preview_runtime_activation_queue_writer_boundary({})

    assert result["scheduler_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_loop_started"] is False


def test_queue_writer_boundary_snapshots_identity_lineage_and_future_record():
    from core.runtime.runtime_activation_queue_writer_boundary import (
        preview_runtime_activation_queue_writer_boundary,
    )

    persistence = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_queue_writer_boundary(persistence)

    assert persistence == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == ["extra", "identity_snapshot", "lineage_snapshot"]
    assert result["identity_snapshot"] == {
        "task_id": "task-1",
        "task_name": "Preview",
    }
    assert result["lineage_snapshot"] == {
        "lineage_id": "lineage-1",
        "trace_id": "trace-1",
    }
    assert result["future_queue_record_preview"] == {
        "record_type": "runtime_queue_task",
        "record_status": "future_package",
        "write_enabled": False,
        "identity_keys": ["task_id", "task_name"],
        "lineage_keys": ["lineage_id", "trace_id"],
    }


def test_queue_writer_boundary_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_queue_writer_boundary import (
        preview_runtime_activation_queue_writer_boundary,
    )

    none_result = preview_runtime_activation_queue_writer_boundary(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["queue_writer_available"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_queue_writer_boundary(malformed)
        assert result["queue_writer_available"] is False
        assert result["queue_record_write_allowed"] is False
        assert result["queue_file_write_allowed"] is False
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
    assert not any("scheduler" in module.lower() for module in imported_modules)
    assert not any("executor" in module.lower() for module in imported_modules)
    assert not any("subprocess" in module.lower() for module in imported_modules)
    assert not any("tool" in module.lower() for module in imported_modules)


def test_docs_explain_disabled_writer_boundary():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "must not write any queue record",
        "Queue writes are forbidden",
        "Queue record writes are forbidden",
        "Queue file writes are forbidden",
        "File IO is forbidden",
        "Queue implementation imports are forbidden",
        "Scheduler imports and calls are forbidden",
        "Executor imports and calls are forbidden",
        "Tool execution is forbidden",
        "GO only for disabled queue writer boundary preview",
    ):
        assert phrase in text


def test_package_sequence_records_873_880():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 873-880" in text
    assert "Runtime Queue Writer Contract Boundary (Disabled)" in text
