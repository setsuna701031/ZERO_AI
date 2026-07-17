import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_executor_execution_completion.py"
DOC = ROOT / "docs/runtime_activation_executor_execution_completion.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_executor_execution_completion_imports_and_public_api_exists():
    from core.runtime import runtime_activation_executor_execution_completion

    assert hasattr(
        runtime_activation_executor_execution_completion,
        "preview_runtime_activation_executor_execution_completion",
    )
    assert runtime_activation_executor_execution_completion.__all__ == [
        "preview_runtime_activation_executor_execution_completion"
    ]


def test_executor_execution_completion_preview_is_deterministic():
    from core.runtime.runtime_activation_executor_execution_completion import (
        preview_runtime_activation_executor_execution_completion,
    )

    start = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
        "execution_start_status": "disabled",
        "execution_start_reason": "executor_execution_start_disabled",
        "execution_started": False,
    }

    first = preview_runtime_activation_executor_execution_completion(start)
    second = preview_runtime_activation_executor_execution_completion(start)

    assert first == second
    assert first["mode"] == "executor_execution_completion_preview"
    assert first["completion_status"] == "disabled"
    assert first["completion_reason"] == "executor_execution_completion_disabled"
    assert first["result"] == "blocked"


def test_executor_execution_completion_remains_disabled():
    from core.runtime.runtime_activation_executor_execution_completion import (
        preview_runtime_activation_executor_execution_completion,
    )

    result = preview_runtime_activation_executor_execution_completion({})

    assert result["execution_completion_ready"] is True
    assert result["execution_completed"] is False
    assert result["execution_result_created"] is False
    assert result["result_commit_allowed"] is False
    assert result["queue_update_allowed"] is False
    assert result["state_transition_allowed"] is False
    assert result["execution_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["tool_call_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["repo_mutation_allowed"] is False


def test_executor_execution_completion_prepares_future_completion_metadata():
    from core.runtime.runtime_activation_executor_execution_completion import (
        preview_runtime_activation_executor_execution_completion,
    )

    result = preview_runtime_activation_executor_execution_completion({})

    assert result["execution_completion_preview"] == {
        "completion_layer": "runtime_executor_execution_completion",
        "execution_completed": False,
        "execution_result_created": False,
        "result_commit_enabled": False,
        "queue_update_enabled": False,
        "state_transition_enabled": False,
        "repo_mutation_enabled": False,
    }


def test_executor_execution_completion_preserves_start_metadata():
    from core.runtime.runtime_activation_executor_execution_completion import (
        preview_runtime_activation_executor_execution_completion,
    )

    start = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "execution_start_status": "disabled",
        "execution_start_reason": "executor_execution_start_disabled",
        "execution_start_boundary_ready": True,
        "executor_runtime_available": False,
        "execution_start_requested": False,
        "execution_start_allowed": False,
        "execution_started": False,
        "execution_completed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "execution_authorization_snapshot": {
            "authorization_status": "disabled",
            "execution_authorized": False,
        },
        "execution_start_preview": {
            "start_layer": "runtime_executor_execution_start",
            "execution_started": False,
        },
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "execution_start_status": "disabled",
        "execution_start_reason": "executor_execution_start_disabled",
        "execution_start_boundary_ready": True,
        "executor_runtime_available": False,
        "execution_start_requested": False,
        "execution_start_allowed": False,
        "execution_started": False,
        "execution_completed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "execution_authorization_snapshot": {
            "authorization_status": "disabled",
            "execution_authorized": False,
        },
        "execution_start_preview": {
            "start_layer": "runtime_executor_execution_start",
            "execution_started": False,
        },
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_executor_execution_completion(start)

    assert start == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == [
        "execution_allowed",
        "execution_authorization_snapshot",
        "execution_completed",
        "execution_start_allowed",
        "execution_start_boundary_ready",
        "execution_start_preview",
        "execution_start_reason",
        "execution_start_requested",
        "execution_start_status",
        "execution_started",
        "executor_runtime_available",
        "extra",
        "identity_snapshot",
        "lineage_snapshot",
        "repo_mutation_allowed",
        "runtime_mutation_allowed",
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
    assert result["execution_start_snapshot"] == {
        "execution_start_status": "disabled",
        "execution_start_reason": "executor_execution_start_disabled",
        "execution_start_boundary_ready": True,
        "executor_runtime_available": False,
        "execution_start_requested": False,
        "execution_start_allowed": False,
        "execution_started": False,
        "execution_completed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "execution_authorization_snapshot": {
            "authorization_status": "disabled",
            "execution_authorized": False,
        },
        "execution_start_preview": {
            "execution_started": False,
            "start_layer": "runtime_executor_execution_start",
        },
    }


def test_executor_execution_completion_has_no_io_or_mutation_flags():
    from core.runtime.runtime_activation_executor_execution_completion import (
        preview_runtime_activation_executor_execution_completion,
    )

    result = preview_runtime_activation_executor_execution_completion({})

    assert result["queue_read_allowed"] is False
    assert result["queue_write_allowed"] is False
    assert result["filesystem_io_allowed"] is False
    assert result["database_io_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_executor_execution_completion_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_executor_execution_completion import (
        preview_runtime_activation_executor_execution_completion,
    )

    result = preview_runtime_activation_executor_execution_completion({})

    assert result["scheduler_runtime_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_import_allowed"] is False
    assert result["tool_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False


def test_executor_execution_completion_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_executor_execution_completion import (
        preview_runtime_activation_executor_execution_completion,
    )

    none_result = preview_runtime_activation_executor_execution_completion(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["execution_completed"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_executor_execution_completion(malformed)
        assert result["execution_completed"] is False
        assert result["execution_result_created"] is False
        assert result["result_commit_allowed"] is False
        assert result["queue_update_allowed"] is False
        assert result["state_transition_allowed"] is False
        assert result["execution_allowed"] is False
        assert result["tool_execution_allowed"] is False
        assert result["tool_call_allowed"] is False
        assert result["runtime_mutation_allowed"] is False
        assert result["repo_mutation_allowed"] is False


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
                    "read",
                    "run",
                    "call",
                    "start",
                    "execute",
                    "commit",
                    "rollback",
                }

    assert not any("queue" in module.lower() for module in imported_modules)
    assert not any("storage" in module.lower() for module in imported_modules)
    assert not any("sqlite" in module.lower() for module in imported_modules)
    assert not any("database" in module.lower() for module in imported_modules)
    assert not any("scheduler" in module.lower() for module in imported_modules)
    assert not any("executor" in module.lower() for module in imported_modules)
    assert not any("subprocess" in module.lower() for module in imported_modules)
    assert not any("tool" in module.lower() for module in imported_modules)


def test_docs_explain_disabled_executor_execution_completion():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "disabled executor execution completion boundary",
        "Tool imports and calls are forbidden",
        "Executor imports and calls are forbidden",
        "Result commits are forbidden",
        "State transitions are forbidden",
        "Queue updates are forbidden",
        "GO only for disabled executor execution completion preview",
    ):
        assert phrase in text


def test_package_sequence_records_1041_1048():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 1041-1048" in text
    assert "Runtime Executor Execution Completion Boundary (Disabled)" in text
