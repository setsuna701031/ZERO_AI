import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_queue_mutation_result.py"
DOC = ROOT / "docs/runtime_activation_queue_mutation_result.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_queue_mutation_result_imports_and_public_api_exists():
    from core.runtime import runtime_activation_queue_mutation_result

    assert hasattr(
        runtime_activation_queue_mutation_result,
        "preview_runtime_activation_queue_mutation_result",
    )
    assert runtime_activation_queue_mutation_result.__all__ == [
        "preview_runtime_activation_queue_mutation_result"
    ]


def test_queue_mutation_result_envelope_is_deterministic():
    from core.runtime.runtime_activation_queue_mutation_result import (
        preview_runtime_activation_queue_mutation_result,
    )

    executor = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
        "executor_shell_status": "disabled",
        "executor_shell_reason": "queue_mutation_executor_shell_disabled",
        "mutation_execution_completed": False,
    }

    first = preview_runtime_activation_queue_mutation_result(executor)
    second = preview_runtime_activation_queue_mutation_result(executor)

    assert first == second
    assert first["mode"] == "queue_mutation_result_preview"
    assert first["result_status"] == "disabled"
    assert first["result_reason"] == "queue_mutation_result_disabled"
    assert first["result"] == "blocked"


def test_queue_mutation_result_keeps_result_commit_disabled():
    from core.runtime.runtime_activation_queue_mutation_result import (
        preview_runtime_activation_queue_mutation_result,
    )

    result = preview_runtime_activation_queue_mutation_result({})

    assert result["result_boundary_ready"] is True
    assert result["mutation_result_created"] is False
    assert result["mutation_success_recorded"] is False
    assert result["queue_state_update_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["transaction_commit_allowed"] is False


def test_queue_mutation_result_allows_no_state_update():
    from core.runtime.runtime_activation_queue_mutation_result import (
        preview_runtime_activation_queue_mutation_result,
    )

    result = preview_runtime_activation_queue_mutation_result({})

    assert result["queue_write_allowed"] is False
    assert result["state_update_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False
    assert result["mutation_result_preview"]["queue_state_update_enabled"] is False
    assert result["mutation_result_preview"]["runtime_update_enabled"] is False


def test_queue_mutation_result_preserves_executor_metadata():
    from core.runtime.runtime_activation_queue_mutation_result import (
        preview_runtime_activation_queue_mutation_result,
    )

    executor = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "executor_shell_status": "disabled",
        "executor_shell_reason": "queue_mutation_executor_shell_disabled",
        "executor_shell_ready": True,
        "mutation_executor_available": False,
        "mutation_execution_started": False,
        "mutation_execution_completed": False,
        "final_gate_snapshot": {
            "final_gate_status": "disabled",
            "mutation_execution_authorized": False,
        },
        "future_executor_shell_preview": {
            "executor_available": False,
            "execution_start_enabled": False,
        },
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "executor_shell_status": "disabled",
        "executor_shell_reason": "queue_mutation_executor_shell_disabled",
        "executor_shell_ready": True,
        "mutation_executor_available": False,
        "mutation_execution_started": False,
        "mutation_execution_completed": False,
        "final_gate_snapshot": {
            "final_gate_status": "disabled",
            "mutation_execution_authorized": False,
        },
        "future_executor_shell_preview": {
            "executor_available": False,
            "execution_start_enabled": False,
        },
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_queue_mutation_result(executor)

    assert executor == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == [
        "executor_shell_ready",
        "executor_shell_reason",
        "executor_shell_status",
        "extra",
        "final_gate_snapshot",
        "future_executor_shell_preview",
        "identity_snapshot",
        "lineage_snapshot",
        "mutation_execution_completed",
        "mutation_execution_started",
        "mutation_executor_available",
    ]
    assert result["identity_snapshot"] == {
        "task_id": "task-1",
        "task_name": "Preview",
    }
    assert result["lineage_snapshot"] == {
        "lineage_id": "lineage-1",
        "trace_id": "trace-1",
    }
    assert result["executor_snapshot"] == {
        "executor_shell_status": "disabled",
        "executor_shell_reason": "queue_mutation_executor_shell_disabled",
        "executor_shell_ready": True,
        "mutation_executor_available": False,
        "mutation_execution_started": False,
        "mutation_execution_completed": False,
        "final_gate_snapshot": {
            "final_gate_status": "disabled",
            "mutation_execution_authorized": False,
        },
        "future_executor_shell_preview": {
            "execution_start_enabled": False,
            "executor_available": False,
        },
    }


def test_queue_mutation_result_prepares_future_result_shape():
    from core.runtime.runtime_activation_queue_mutation_result import (
        preview_runtime_activation_queue_mutation_result,
    )

    result = preview_runtime_activation_queue_mutation_result({})

    assert result["mutation_result_preview"] == {
        "result_type": "runtime_queue_mutation",
        "result_created": False,
        "success_recorded": False,
        "queue_state_update_enabled": False,
        "runtime_update_enabled": False,
        "commit_enabled": False,
    }


def test_queue_mutation_result_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_queue_mutation_result import (
        preview_runtime_activation_queue_mutation_result,
    )

    result = preview_runtime_activation_queue_mutation_result({})

    assert result["scheduler_call_allowed"] is False
    assert result["executor_runtime_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False


def test_queue_mutation_result_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_queue_mutation_result import (
        preview_runtime_activation_queue_mutation_result,
    )

    none_result = preview_runtime_activation_queue_mutation_result(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["mutation_result_created"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_queue_mutation_result(malformed)
        assert result["mutation_result_created"] is False
        assert result["mutation_success_recorded"] is False
        assert result["queue_state_update_allowed"] is False
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
    assert not any("storage" in module.lower() for module in imported_modules)
    assert not any("sqlite" in module.lower() for module in imported_modules)
    assert not any("database" in module.lower() for module in imported_modules)
    assert not any("scheduler" in module.lower() for module in imported_modules)
    assert not any("executor" in module.lower() for module in imported_modules)
    assert not any("subprocess" in module.lower() for module in imported_modules)
    assert not any("tool" in module.lower() for module in imported_modules)


def test_docs_explain_disabled_mutation_result_envelope():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "must not execute or persist mutation",
        "Queue writes are forbidden",
        "State updates are forbidden",
        "Transaction commit is forbidden",
        "Scheduler imports and calls are forbidden",
        "Executor runtime imports and calls are forbidden",
        "Tool execution is forbidden",
        "Runtime mutation is forbidden",
        "GO only for disabled queue mutation result envelope preview",
    ):
        assert phrase in text


def test_package_sequence_records_945_952():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 945-952" in text
    assert "Runtime Queue Mutation Result Envelope (Disabled)" in text
