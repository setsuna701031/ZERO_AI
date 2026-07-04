import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_queue_commit_gate.py"
DOC = ROOT / "docs/runtime_activation_queue_commit_gate.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_queue_commit_gate_imports_and_public_api_exists():
    from core.runtime import runtime_activation_queue_commit_gate

    assert hasattr(
        runtime_activation_queue_commit_gate,
        "preview_runtime_activation_queue_commit_gate",
    )
    assert runtime_activation_queue_commit_gate.__all__ == [
        "preview_runtime_activation_queue_commit_gate"
    ]


def test_queue_commit_gate_preview_is_deterministic():
    from core.runtime.runtime_activation_queue_commit_gate import (
        preview_runtime_activation_queue_commit_gate,
    )

    admission = {
        "task_identity": {"task_id": "task-1", "task_name": "Preview"},
        "lineage": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
    }

    first = preview_runtime_activation_queue_commit_gate(admission)
    second = preview_runtime_activation_queue_commit_gate(admission)

    assert first == second
    assert first["mode"] == "queue_commit_gate_preview"
    assert first["commit_reason"] == "queue_commit_disabled"
    assert first["result"] == "blocked"
    assert first["reason"] == "queue_commit_gate_disabled"


def test_queue_commit_gate_keeps_mutation_and_persistence_disabled():
    from core.runtime.runtime_activation_queue_commit_gate import (
        preview_runtime_activation_queue_commit_gate,
    )

    result = preview_runtime_activation_queue_commit_gate({})

    assert result["commit_gate_ready"] is True
    assert result["queue_commit_allowed"] is False
    assert result["mutation_allowed"] is False
    assert result["persistence_allowed"] is False
    assert result["queue_write_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_queue_commit_gate_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_queue_commit_gate import (
        preview_runtime_activation_queue_commit_gate,
    )

    result = preview_runtime_activation_queue_commit_gate({})

    assert result["scheduler_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False


def test_queue_commit_gate_snapshots_identity_and_lineage_without_mutating_input():
    from core.runtime.runtime_activation_queue_commit_gate import (
        preview_runtime_activation_queue_commit_gate,
    )

    admission = {
        "task_identity": {"task_id": "task-1", "task_name": "Preview"},
        "lineage": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "extra": {"nested": True},
    }
    original = {
        "task_identity": {"task_id": "task-1", "task_name": "Preview"},
        "lineage": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_queue_commit_gate(admission)

    assert admission == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == ["extra", "lineage", "task_identity"]
    assert result["identity_snapshot"] == {
        "task_id": "task-1",
        "task_name": "Preview",
    }
    assert result["lineage_snapshot"] == {
        "lineage_id": "lineage-1",
        "trace_id": "trace-1",
    }


def test_queue_commit_gate_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_queue_commit_gate import (
        preview_runtime_activation_queue_commit_gate,
    )

    none_result = preview_runtime_activation_queue_commit_gate(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["queue_commit_allowed"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_queue_commit_gate(malformed)
        assert result["queue_commit_allowed"] is False
        assert result["mutation_allowed"] is False
        assert result["persistence_allowed"] is False


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


def test_docs_explain_last_disabled_gate_before_future_persistence():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "last disabled gate before future queue persistence",
        "Queue writes are forbidden",
        "Queue implementation imports are forbidden",
        "Scheduler imports and calls are forbidden",
        "Executor imports and calls are forbidden",
        "File IO is forbidden",
        "Subprocess use is forbidden",
        "Tool execution is forbidden",
        "Runtime state mutation is forbidden",
        "GO only for disabled queue commit gate preview",
    ):
        assert phrase in text


def test_package_sequence_records_857_864():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 857-864" in text
    assert "Runtime Queue Commit Gate (Disabled)" in text
