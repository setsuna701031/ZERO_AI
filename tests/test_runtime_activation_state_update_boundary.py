import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_state_update_boundary.py"
DOC = ROOT / "docs/runtime_activation_state_update_boundary.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_state_update_imports_and_public_api_exists():
    from core.runtime import runtime_activation_state_update_boundary

    assert hasattr(
        runtime_activation_state_update_boundary,
        "preview_runtime_activation_state_update",
    )
    assert runtime_activation_state_update_boundary.__all__ == [
        "preview_runtime_activation_state_update"
    ]


def test_state_update_preview_is_deterministic():
    from core.runtime.runtime_activation_state_update_boundary import (
        preview_runtime_activation_state_update,
    )

    persistence = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
        "persistence_status": "disabled",
        "persistence_reason": "executor_result_persistence_disabled",
        "result_persisted": False,
    }

    first = preview_runtime_activation_state_update(persistence)
    second = preview_runtime_activation_state_update(persistence)

    assert first == second
    assert first["mode"] == "runtime_state_update_preview"
    assert first["state_update_status"] == "disabled"
    assert first["state_update_reason"] == "runtime_state_update_disabled"
    assert first["result"] == "blocked"


def test_state_update_remains_disabled():
    from core.runtime.runtime_activation_state_update_boundary import (
        preview_runtime_activation_state_update,
    )

    result = preview_runtime_activation_state_update({})

    assert result["state_update_ready"] is True
    assert result["state_update_allowed"] is False
    assert result["runtime_state_updated"] is False
    assert result["task_state_updated"] is False
    assert result["queue_state_updated"] is False
    assert result["state_persistence_allowed"] is False
    assert result["task_lifecycle_transition_allowed"] is False
    assert result["queue_finalization_allowed"] is False
    assert result["execution_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["tool_call_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["repo_mutation_allowed"] is False


def test_state_update_prepares_future_update_metadata():
    from core.runtime.runtime_activation_state_update_boundary import (
        preview_runtime_activation_state_update,
    )

    result = preview_runtime_activation_state_update({})

    assert result["state_update_preview"] == {
        "state_update_layer": "runtime_activation_state_update",
        "runtime_state_updated": False,
        "task_state_updated": False,
        "queue_state_updated": False,
        "state_update_enabled": False,
        "task_lifecycle_transition_enabled": False,
        "queue_finalization_enabled": False,
    }


def test_state_update_preserves_result_persistence_metadata():
    from core.runtime.runtime_activation_state_update_boundary import (
        preview_runtime_activation_state_update,
    )

    persistence = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "persistence_status": "disabled",
        "persistence_reason": "executor_result_persistence_disabled",
        "result_persistence_ready": True,
        "result_persisted": False,
        "persistence_allowed": False,
        "state_update_allowed": False,
        "queue_update_allowed": False,
        "state_transition_allowed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "result_commit_snapshot": {
            "commit_status": "disabled",
            "result_commit_executed": False,
        },
        "result_persistence_preview": {
            "persistence_layer": "runtime_executor_result_persistence",
            "result_persisted": False,
        },
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "persistence_status": "disabled",
        "persistence_reason": "executor_result_persistence_disabled",
        "result_persistence_ready": True,
        "result_persisted": False,
        "persistence_allowed": False,
        "state_update_allowed": False,
        "queue_update_allowed": False,
        "state_transition_allowed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "result_commit_snapshot": {
            "commit_status": "disabled",
            "result_commit_executed": False,
        },
        "result_persistence_preview": {
            "persistence_layer": "runtime_executor_result_persistence",
            "result_persisted": False,
        },
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_state_update(persistence)

    assert persistence == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == [
        "execution_allowed",
        "extra",
        "identity_snapshot",
        "lineage_snapshot",
        "persistence_allowed",
        "persistence_reason",
        "persistence_status",
        "queue_update_allowed",
        "repo_mutation_allowed",
        "result_commit_snapshot",
        "result_persisted",
        "result_persistence_preview",
        "result_persistence_ready",
        "runtime_mutation_allowed",
        "state_transition_allowed",
        "state_update_allowed",
        "tool_call_allowed",
        "tool_execution_allowed",
    ]
    assert result["identity_snapshot"] == {
        "task_id": "task-1",
        "task_name": "Preview",
    }
    assert result["lineage_snapshot"] == {
        "lineage_id": "lineage-1",
        "trace_id": "trace-1",
    }
    assert result["result_persistence_snapshot"] == {
        "persistence_status": "disabled",
        "persistence_reason": "executor_result_persistence_disabled",
        "result_persistence_ready": True,
        "result_persisted": False,
        "persistence_allowed": False,
        "state_update_allowed": False,
        "queue_update_allowed": False,
        "state_transition_allowed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "result_commit_snapshot": {
            "commit_status": "disabled",
            "result_commit_executed": False,
        },
        "result_persistence_preview": {
            "persistence_layer": "runtime_executor_result_persistence",
            "result_persisted": False,
        },
    }


def test_state_update_has_no_io_or_mutation_flags():
    from core.runtime.runtime_activation_state_update_boundary import (
        preview_runtime_activation_state_update,
    )

    result = preview_runtime_activation_state_update({})

    assert result["queue_read_allowed"] is False
    assert result["queue_write_allowed"] is False
    assert result["filesystem_io_allowed"] is False
    assert result["database_io_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_state_update_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_state_update_boundary import (
        preview_runtime_activation_state_update,
    )

    result = preview_runtime_activation_state_update({})

    assert result["scheduler_runtime_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_import_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False


def test_state_update_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_state_update_boundary import (
        preview_runtime_activation_state_update,
    )

    none_result = preview_runtime_activation_state_update(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["runtime_state_updated"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_state_update(malformed)
        assert result["state_update_allowed"] is False
        assert result["runtime_state_updated"] is False
        assert result["task_state_updated"] is False
        assert result["queue_state_updated"] is False
        assert result["tool_execution_allowed"] is False
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
        "save",
        "update",
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
                    "read",
                    "run",
                    "call",
                    "start",
                    "execute",
                    "commit",
                    "rollback",
                    "save",
                    "update",
                    "transition",
                }

    assert not any("queue" in module.lower() for module in imported_modules)
    assert not any("storage" in module.lower() for module in imported_modules)
    assert not any("sqlite" in module.lower() for module in imported_modules)
    assert not any("database" in module.lower() for module in imported_modules)
    assert not any("scheduler" in module.lower() for module in imported_modules)
    assert not any("executor" in module.lower() for module in imported_modules)
    assert not any("subprocess" in module.lower() for module in imported_modules)
    assert not any("tool" in module.lower() for module in imported_modules)
    assert not any("state_machine" in module.lower() for module in imported_modules)


def test_docs_explain_disabled_state_update():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "must not update runtime, task, or queue state",
        "Runtime state machine imports and calls are forbidden",
        "Task state updates are forbidden",
        "Queue updates are forbidden",
        "Executor imports and calls are forbidden",
        "Tool imports and calls are forbidden",
        "GO only for disabled runtime state update preview",
    ):
        assert phrase in text


def test_package_sequence_records_1065_1072():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 1065-1072" in text
    assert "Runtime State Update Boundary (Disabled)" in text
