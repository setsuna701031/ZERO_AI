import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_task_lifecycle_transition.py"
DOC = ROOT / "docs/runtime_activation_task_lifecycle_transition.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_task_lifecycle_transition_imports_and_public_api_exists():
    from core.runtime import runtime_activation_task_lifecycle_transition

    assert hasattr(
        runtime_activation_task_lifecycle_transition,
        "preview_runtime_activation_task_lifecycle_transition",
    )
    assert runtime_activation_task_lifecycle_transition.__all__ == [
        "preview_runtime_activation_task_lifecycle_transition"
    ]


def test_task_lifecycle_transition_preview_is_deterministic():
    from core.runtime.runtime_activation_task_lifecycle_transition import (
        preview_runtime_activation_task_lifecycle_transition,
    )

    state_update = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
        "state_update_status": "disabled",
        "state_update_reason": "runtime_state_update_disabled",
        "runtime_state_updated": False,
    }

    first = preview_runtime_activation_task_lifecycle_transition(state_update)
    second = preview_runtime_activation_task_lifecycle_transition(state_update)

    assert first == second
    assert first["mode"] == "runtime_task_lifecycle_transition_preview"
    assert first["transition_status"] == "disabled"
    assert first["transition_reason"] == "runtime_task_lifecycle_transition_disabled"
    assert first["result"] == "blocked"


def test_task_lifecycle_transition_remains_disabled():
    from core.runtime.runtime_activation_task_lifecycle_transition import (
        preview_runtime_activation_task_lifecycle_transition,
    )

    result = preview_runtime_activation_task_lifecycle_transition({})

    assert result["transition_boundary_ready"] is True
    assert result["task_lifecycle_transition_ready"] is True
    assert result["task_lifecycle_transition_allowed"] is False
    assert result["task_transition_allowed"] is False
    assert result["queue_transition_allowed"] is False
    assert result["runtime_transition_allowed"] is False
    assert result["task_state_changed"] is False
    assert result["queue_state_changed"] is False
    assert result["runtime_state_changed"] is False
    assert result["queue_finalization_allowed"] is False
    assert result["execution_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["repo_mutation_allowed"] is False


def test_task_lifecycle_transition_prepares_future_transition_metadata():
    from core.runtime.runtime_activation_task_lifecycle_transition import (
        preview_runtime_activation_task_lifecycle_transition,
    )

    result = preview_runtime_activation_task_lifecycle_transition({})

    assert result["task_lifecycle_transition_preview"] == {
        "transition_layer": "runtime_activation_task_lifecycle_transition",
        "task_state_changed": False,
        "queue_state_changed": False,
        "runtime_state_changed": False,
        "task_lifecycle_transition_enabled": False,
        "queue_finalization_enabled": False,
    }


def test_task_lifecycle_transition_preserves_state_update_metadata():
    from core.runtime.runtime_activation_task_lifecycle_transition import (
        preview_runtime_activation_task_lifecycle_transition,
    )

    state_update = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "state_update_status": "disabled",
        "state_update_reason": "runtime_state_update_disabled",
        "state_update_ready": True,
        "state_update_allowed": False,
        "runtime_state_updated": False,
        "task_state_updated": False,
        "queue_state_updated": False,
        "state_persistence_allowed": False,
        "task_lifecycle_transition_allowed": False,
        "queue_finalization_allowed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "result_persistence_snapshot": {
            "persistence_status": "disabled",
            "result_persisted": False,
        },
        "state_update_preview": {
            "state_update_layer": "runtime_activation_state_update",
            "runtime_state_updated": False,
        },
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "state_update_status": "disabled",
        "state_update_reason": "runtime_state_update_disabled",
        "state_update_ready": True,
        "state_update_allowed": False,
        "runtime_state_updated": False,
        "task_state_updated": False,
        "queue_state_updated": False,
        "state_persistence_allowed": False,
        "task_lifecycle_transition_allowed": False,
        "queue_finalization_allowed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "result_persistence_snapshot": {
            "persistence_status": "disabled",
            "result_persisted": False,
        },
        "state_update_preview": {
            "state_update_layer": "runtime_activation_state_update",
            "runtime_state_updated": False,
        },
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_task_lifecycle_transition(state_update)

    assert state_update == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == [
        "execution_allowed",
        "extra",
        "identity_snapshot",
        "lineage_snapshot",
        "queue_finalization_allowed",
        "queue_state_updated",
        "repo_mutation_allowed",
        "result_persistence_snapshot",
        "runtime_mutation_allowed",
        "runtime_state_updated",
        "state_persistence_allowed",
        "state_update_allowed",
        "state_update_preview",
        "state_update_ready",
        "state_update_reason",
        "state_update_status",
        "task_lifecycle_transition_allowed",
        "task_state_updated",
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
    assert result["state_update_snapshot"] == {
        "state_update_status": "disabled",
        "state_update_reason": "runtime_state_update_disabled",
        "state_update_ready": True,
        "state_update_allowed": False,
        "runtime_state_updated": False,
        "task_state_updated": False,
        "queue_state_updated": False,
        "state_persistence_allowed": False,
        "task_lifecycle_transition_allowed": False,
        "queue_finalization_allowed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "result_persistence_snapshot": {
            "persistence_status": "disabled",
            "result_persisted": False,
        },
        "state_update_preview": {
            "state_update_layer": "runtime_activation_state_update",
            "runtime_state_updated": False,
        },
    }


def test_task_lifecycle_transition_has_no_io_or_mutation_flags():
    from core.runtime.runtime_activation_task_lifecycle_transition import (
        preview_runtime_activation_task_lifecycle_transition,
    )

    result = preview_runtime_activation_task_lifecycle_transition({})

    assert result["queue_read_allowed"] is False
    assert result["queue_write_allowed"] is False
    assert result["filesystem_io_allowed"] is False
    assert result["database_io_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_task_lifecycle_transition_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_task_lifecycle_transition import (
        preview_runtime_activation_task_lifecycle_transition,
    )

    result = preview_runtime_activation_task_lifecycle_transition({})

    assert result["scheduler_runtime_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_import_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False


def test_task_lifecycle_transition_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_task_lifecycle_transition import (
        preview_runtime_activation_task_lifecycle_transition,
    )

    none_result = preview_runtime_activation_task_lifecycle_transition(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["task_state_changed"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_task_lifecycle_transition(malformed)
        assert result["task_lifecycle_transition_allowed"] is False
        assert result["task_state_changed"] is False
        assert result["queue_state_changed"] is False
        assert result["runtime_state_changed"] is False
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
        "transition",
        "complete",
        "finalize",
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
                    "complete",
                    "finalize",
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


def test_docs_explain_disabled_task_lifecycle_transition():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "must not change task, queue, or runtime state",
        "Task lifecycle updates are forbidden",
        "Queue finalization is forbidden",
        "Runtime state machine imports and calls are forbidden",
        "Scheduler imports and calls are forbidden",
        "Executor imports and calls are forbidden",
        "GO only for disabled task lifecycle transition preview",
    ):
        assert phrase in text


def test_package_sequence_records_1073_1080():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 1073-1080" in text
    assert "Runtime Task Lifecycle Transition Boundary (Disabled)" in text
