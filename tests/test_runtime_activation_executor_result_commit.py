import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_executor_result_commit.py"
DOC = ROOT / "docs/runtime_activation_executor_result_commit.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_executor_result_commit_imports_and_public_api_exists():
    from core.runtime import runtime_activation_executor_result_commit

    assert hasattr(
        runtime_activation_executor_result_commit,
        "preview_runtime_activation_executor_result_commit",
    )
    assert runtime_activation_executor_result_commit.__all__ == [
        "preview_runtime_activation_executor_result_commit"
    ]


def test_executor_result_commit_preview_is_deterministic():
    from core.runtime.runtime_activation_executor_result_commit import (
        preview_runtime_activation_executor_result_commit,
    )

    completion = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
        "completion_status": "disabled",
        "completion_reason": "executor_execution_completion_disabled",
        "execution_completed": False,
    }

    first = preview_runtime_activation_executor_result_commit(completion)
    second = preview_runtime_activation_executor_result_commit(completion)

    assert first == second
    assert first["mode"] == "executor_result_commit_preview"
    assert first["commit_status"] == "disabled"
    assert first["commit_reason"] == "executor_result_commit_disabled"
    assert first["result"] == "blocked"


def test_executor_result_commit_remains_disabled():
    from core.runtime.runtime_activation_executor_result_commit import (
        preview_runtime_activation_executor_result_commit,
    )

    result = preview_runtime_activation_executor_result_commit({})

    assert result["result_commit_boundary_ready"] is True
    assert result["result_commit_prepared"] is True
    assert result["result_commit_executed"] is False
    assert result["result_persistence_allowed"] is False
    assert result["queue_update_allowed"] is False
    assert result["state_transition_allowed"] is False
    assert result["execution_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["tool_call_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["repo_mutation_allowed"] is False


def test_executor_result_commit_prepares_future_commit_metadata():
    from core.runtime.runtime_activation_executor_result_commit import (
        preview_runtime_activation_executor_result_commit,
    )

    result = preview_runtime_activation_executor_result_commit({})

    assert result["result_commit_preview"] == {
        "commit_layer": "runtime_executor_result_commit",
        "result_commit_executed": False,
        "result_persistence_enabled": False,
        "queue_update_enabled": False,
        "state_transition_enabled": False,
        "repo_mutation_enabled": False,
    }


def test_executor_result_commit_preserves_completion_metadata():
    from core.runtime.runtime_activation_executor_result_commit import (
        preview_runtime_activation_executor_result_commit,
    )

    completion = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "completion_status": "disabled",
        "completion_reason": "executor_execution_completion_disabled",
        "execution_completion_ready": True,
        "execution_completed": False,
        "execution_result_created": False,
        "result_commit_allowed": False,
        "queue_update_allowed": False,
        "state_transition_allowed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "execution_start_snapshot": {
            "execution_start_status": "disabled",
            "execution_started": False,
        },
        "execution_completion_preview": {
            "completion_layer": "runtime_executor_execution_completion",
            "execution_completed": False,
        },
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "completion_status": "disabled",
        "completion_reason": "executor_execution_completion_disabled",
        "execution_completion_ready": True,
        "execution_completed": False,
        "execution_result_created": False,
        "result_commit_allowed": False,
        "queue_update_allowed": False,
        "state_transition_allowed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "execution_start_snapshot": {
            "execution_start_status": "disabled",
            "execution_started": False,
        },
        "execution_completion_preview": {
            "completion_layer": "runtime_executor_execution_completion",
            "execution_completed": False,
        },
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_executor_result_commit(completion)

    assert completion == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == [
        "completion_reason",
        "completion_status",
        "execution_allowed",
        "execution_completed",
        "execution_completion_preview",
        "execution_completion_ready",
        "execution_result_created",
        "execution_start_snapshot",
        "extra",
        "identity_snapshot",
        "lineage_snapshot",
        "queue_update_allowed",
        "repo_mutation_allowed",
        "result_commit_allowed",
        "runtime_mutation_allowed",
        "state_transition_allowed",
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
    assert result["execution_completion_snapshot"] == {
        "completion_status": "disabled",
        "completion_reason": "executor_execution_completion_disabled",
        "execution_completion_ready": True,
        "execution_completed": False,
        "execution_result_created": False,
        "result_commit_allowed": False,
        "queue_update_allowed": False,
        "state_transition_allowed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "execution_start_snapshot": {
            "execution_start_status": "disabled",
            "execution_started": False,
        },
        "execution_completion_preview": {
            "completion_layer": "runtime_executor_execution_completion",
            "execution_completed": False,
        },
    }


def test_executor_result_commit_has_no_io_or_mutation_flags():
    from core.runtime.runtime_activation_executor_result_commit import (
        preview_runtime_activation_executor_result_commit,
    )

    result = preview_runtime_activation_executor_result_commit({})

    assert result["queue_read_allowed"] is False
    assert result["queue_write_allowed"] is False
    assert result["filesystem_io_allowed"] is False
    assert result["database_io_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_executor_result_commit_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_executor_result_commit import (
        preview_runtime_activation_executor_result_commit,
    )

    result = preview_runtime_activation_executor_result_commit({})

    assert result["scheduler_runtime_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_import_allowed"] is False
    assert result["tool_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False


def test_executor_result_commit_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_executor_result_commit import (
        preview_runtime_activation_executor_result_commit,
    )

    none_result = preview_runtime_activation_executor_result_commit(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["result_commit_executed"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_executor_result_commit(malformed)
        assert result["result_commit_executed"] is False
        assert result["result_persistence_allowed"] is False
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


def test_docs_explain_disabled_executor_result_commit():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "disabled executor result commit boundary",
        "Tool imports and calls are forbidden",
        "Executor imports and calls are forbidden",
        "Result commits are forbidden",
        "Result persistence is forbidden",
        "State transitions are forbidden",
        "Queue updates are forbidden",
        "GO only for disabled executor result commit preview",
    ):
        assert phrase in text


def test_package_sequence_records_1049_1056():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 1049-1056" in text
    assert "Runtime Executor Result Commit Boundary (Disabled)" in text
