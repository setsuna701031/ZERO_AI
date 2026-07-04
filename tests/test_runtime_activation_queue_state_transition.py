import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_queue_state_transition.py"
DOC = ROOT / "docs/runtime_activation_queue_state_transition.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_queue_state_transition_imports_and_public_api_exists():
    from core.runtime import runtime_activation_queue_state_transition

    assert hasattr(
        runtime_activation_queue_state_transition,
        "preview_runtime_activation_queue_state_transition",
    )
    assert runtime_activation_queue_state_transition.__all__ == [
        "preview_runtime_activation_queue_state_transition"
    ]


def test_queue_state_transition_preview_is_deterministic():
    from core.runtime.runtime_activation_queue_state_transition import (
        preview_runtime_activation_queue_state_transition,
    )

    result_preview = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
        "result_status": "disabled",
        "result_reason": "queue_mutation_result_disabled",
        "mutation_result_created": False,
    }

    first = preview_runtime_activation_queue_state_transition(result_preview)
    second = preview_runtime_activation_queue_state_transition(result_preview)

    assert first == second
    assert first["mode"] == "queue_state_transition_preview"
    assert first["transition_status"] == "disabled"
    assert first["transition_reason"] == "queue_state_transition_disabled"
    assert first["result"] == "blocked"


def test_queue_state_transition_keeps_queue_state_update_disabled():
    from core.runtime.runtime_activation_queue_state_transition import (
        preview_runtime_activation_queue_state_transition,
    )

    result = preview_runtime_activation_queue_state_transition({})

    assert result["transition_boundary_ready"] is True
    assert result["state_transition_prepared"] is True
    assert result["queue_state_update_allowed"] is False
    assert result["state_persistence_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["queue_state_write_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_queue_state_transition_keeps_persistence_and_commits_disabled():
    from core.runtime.runtime_activation_queue_state_transition import (
        preview_runtime_activation_queue_state_transition,
    )

    result = preview_runtime_activation_queue_state_transition({})

    assert result["persistence_write_allowed"] is False
    assert result["transaction_commit_allowed"] is False
    assert result["future_state_preview"]["state_persistence_enabled"] is False
    assert result["future_state_preview"]["commit_enabled"] is False


def test_queue_state_transition_preserves_result_metadata():
    from core.runtime.runtime_activation_queue_state_transition import (
        preview_runtime_activation_queue_state_transition,
    )

    result_preview = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "result_status": "disabled",
        "result_reason": "queue_mutation_result_disabled",
        "result_boundary_ready": True,
        "mutation_result_created": False,
        "mutation_success_recorded": False,
        "queue_state_update_allowed": False,
        "executor_snapshot": {
            "executor_shell_status": "disabled",
            "mutation_execution_completed": False,
        },
        "mutation_result_preview": {
            "result_type": "runtime_queue_mutation",
            "success_recorded": False,
        },
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "result_status": "disabled",
        "result_reason": "queue_mutation_result_disabled",
        "result_boundary_ready": True,
        "mutation_result_created": False,
        "mutation_success_recorded": False,
        "queue_state_update_allowed": False,
        "executor_snapshot": {
            "executor_shell_status": "disabled",
            "mutation_execution_completed": False,
        },
        "mutation_result_preview": {
            "result_type": "runtime_queue_mutation",
            "success_recorded": False,
        },
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_queue_state_transition(result_preview)

    assert result_preview == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == [
        "executor_snapshot",
        "extra",
        "identity_snapshot",
        "lineage_snapshot",
        "mutation_result_created",
        "mutation_result_preview",
        "mutation_success_recorded",
        "queue_state_update_allowed",
        "result_boundary_ready",
        "result_reason",
        "result_status",
    ]
    assert result["identity_snapshot"] == {
        "task_id": "task-1",
        "task_name": "Preview",
    }
    assert result["lineage_snapshot"] == {
        "lineage_id": "lineage-1",
        "trace_id": "trace-1",
    }
    assert result["mutation_result_snapshot"] == {
        "result_status": "disabled",
        "result_reason": "queue_mutation_result_disabled",
        "result_boundary_ready": True,
        "mutation_result_created": False,
        "mutation_success_recorded": False,
        "queue_state_update_allowed": False,
        "executor_snapshot": {
            "executor_shell_status": "disabled",
            "mutation_execution_completed": False,
        },
        "mutation_result_preview": {
            "result_type": "runtime_queue_mutation",
            "success_recorded": False,
        },
    }


def test_queue_state_transition_prepares_future_state_preview():
    from core.runtime.runtime_activation_queue_state_transition import (
        preview_runtime_activation_queue_state_transition,
    )

    result = preview_runtime_activation_queue_state_transition({})

    assert result["future_state_preview"] == {
        "state_transition_type": "runtime_queue_mutation_result",
        "transition_prepared": True,
        "queue_state_update_enabled": False,
        "state_persistence_enabled": False,
        "runtime_update_enabled": False,
        "commit_enabled": False,
    }


def test_queue_state_transition_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_queue_state_transition import (
        preview_runtime_activation_queue_state_transition,
    )

    result = preview_runtime_activation_queue_state_transition({})

    assert result["scheduler_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False


def test_queue_state_transition_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_queue_state_transition import (
        preview_runtime_activation_queue_state_transition,
    )

    none_result = preview_runtime_activation_queue_state_transition(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["queue_state_update_allowed"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_queue_state_transition(malformed)
        assert result["state_transition_prepared"] is True
        assert result["queue_state_update_allowed"] is False
        assert result["state_persistence_allowed"] is False
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


def test_docs_explain_disabled_state_transition_boundary():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "must not update queue state",
        "Queue state writes are forbidden",
        "Persistence writes are forbidden",
        "Transaction commits are forbidden",
        "Scheduler imports and calls are forbidden",
        "Executor imports and calls are forbidden",
        "Tool execution is forbidden",
        "Runtime mutation is forbidden",
        "GO only for disabled queue state transition preview",
    ):
        assert phrase in text


def test_package_sequence_records_953_960():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 953-960" in text
    assert "Runtime Queue State Transition Boundary (Disabled)" in text
