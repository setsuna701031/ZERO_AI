import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_queue_transaction_boundary.py"
DOC = ROOT / "docs/runtime_activation_queue_transaction_boundary.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_queue_transaction_boundary_imports_and_public_api_exists():
    from core.runtime import runtime_activation_queue_transaction_boundary

    assert hasattr(
        runtime_activation_queue_transaction_boundary,
        "preview_runtime_activation_queue_transaction_boundary",
    )
    assert runtime_activation_queue_transaction_boundary.__all__ == [
        "preview_runtime_activation_queue_transaction_boundary"
    ]


def test_queue_transaction_boundary_preview_is_deterministic():
    from core.runtime.runtime_activation_queue_transaction_boundary import (
        preview_runtime_activation_queue_transaction_boundary,
    )

    storage = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
    }

    first = preview_runtime_activation_queue_transaction_boundary(storage)
    second = preview_runtime_activation_queue_transaction_boundary(storage)

    assert first == second
    assert first["mode"] == "queue_transaction_boundary_preview"
    assert first["transaction_status"] == "disabled"
    assert first["transaction_reason"] == "queue_transaction_disabled"
    assert first["result"] == "blocked"


def test_queue_transaction_boundary_keeps_transactions_and_mutation_disabled():
    from core.runtime.runtime_activation_queue_transaction_boundary import (
        preview_runtime_activation_queue_transaction_boundary,
    )

    result = preview_runtime_activation_queue_transaction_boundary({})

    assert result["transaction_boundary_ready"] is True
    assert result["transaction_available"] is False
    assert result["transaction_begin_allowed"] is False
    assert result["transaction_commit_allowed"] is False
    assert result["transaction_rollback_available"] is False
    assert result["queue_mutation_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["filesystem_write_allowed"] is False
    assert result["database_write_allowed"] is False


def test_queue_transaction_boundary_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_queue_transaction_boundary import (
        preview_runtime_activation_queue_transaction_boundary,
    )

    result = preview_runtime_activation_queue_transaction_boundary({})

    assert result["scheduler_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_queue_transaction_boundary_snapshots_metadata_and_future_transaction():
    from core.runtime.runtime_activation_queue_transaction_boundary import (
        preview_runtime_activation_queue_transaction_boundary,
    )

    storage = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_queue_transaction_boundary(storage)

    assert storage == original
    assert result["identity_snapshot"] == {
        "task_id": "task-1",
        "task_name": "Preview",
    }
    assert result["lineage_snapshot"] == {
        "lineage_id": "lineage-1",
        "trace_id": "trace-1",
    }
    assert result["future_transaction_preview"] == {
        "transaction_type": "persistent_queue_mutation",
        "begin_enabled": False,
        "commit_enabled": False,
        "rollback_available": False,
        "write_enabled": False,
    }


def test_queue_transaction_boundary_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_queue_transaction_boundary import (
        preview_runtime_activation_queue_transaction_boundary,
    )

    none_result = preview_runtime_activation_queue_transaction_boundary(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["transaction_available"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_queue_transaction_boundary(malformed)
        assert result["transaction_available"] is False
        assert result["transaction_begin_allowed"] is False
        assert result["transaction_commit_allowed"] is False
        assert result["queue_mutation_allowed"] is False
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
        "connect",
        "execute",
        "commit",
        "rollback",
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
                assert node.func.attr not in {
                    "write",
                    "run",
                    "call",
                    "start",
                    "execute",
                    "commit",
                    "rollback",
                }

    assert not any("queue" in module.lower() for module in imported_modules)
    assert not any("sqlite" in module.lower() for module in imported_modules)
    assert not any("database" in module.lower() for module in imported_modules)
    assert not any("scheduler" in module.lower() for module in imported_modules)
    assert not any("executor" in module.lower() for module in imported_modules)
    assert not any("subprocess" in module.lower() for module in imported_modules)
    assert not any("tool" in module.lower() for module in imported_modules)


def test_docs_explain_disabled_transaction_boundary():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "must not perform queue transactions or writes",
        "Database transactions are forbidden",
        "Filesystem writes are forbidden",
        "Queue mutation is forbidden",
        "Scheduler imports and calls are forbidden",
        "Executor imports and calls are forbidden",
        "Tool execution is forbidden",
        "Transaction begin is forbidden",
        "GO only for disabled queue transaction boundary preview",
    ):
        assert phrase in text


def test_package_sequence_records_897_904():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 897-904" in text
    assert "Runtime Queue Transaction Boundary (Disabled)" in text
