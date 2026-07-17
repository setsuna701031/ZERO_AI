import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_queue_mutation_executor_shell.py"
DOC = ROOT / "docs/runtime_activation_queue_mutation_executor_shell.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_queue_mutation_executor_shell_imports_and_public_api_exists():
    from core.runtime import runtime_activation_queue_mutation_executor_shell

    assert hasattr(
        runtime_activation_queue_mutation_executor_shell,
        "preview_runtime_activation_queue_mutation_executor_shell",
    )
    assert runtime_activation_queue_mutation_executor_shell.__all__ == [
        "preview_runtime_activation_queue_mutation_executor_shell"
    ]


def test_queue_mutation_executor_shell_preview_is_deterministic():
    from core.runtime.runtime_activation_queue_mutation_executor_shell import (
        preview_runtime_activation_queue_mutation_executor_shell,
    )

    final_gate = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
        "final_gate_status": "disabled",
        "final_gate_reason": "queue_mutation_final_gate_disabled",
        "safety_check_passed": True,
    }

    first = preview_runtime_activation_queue_mutation_executor_shell(final_gate)
    second = preview_runtime_activation_queue_mutation_executor_shell(final_gate)

    assert first == second
    assert first["mode"] == "queue_mutation_executor_shell_preview"
    assert first["executor_shell_status"] == "disabled"
    assert first["executor_shell_reason"] == "queue_mutation_executor_shell_disabled"
    assert first["result"] == "blocked"


def test_queue_mutation_executor_shell_keeps_execution_disabled():
    from core.runtime.runtime_activation_queue_mutation_executor_shell import (
        preview_runtime_activation_queue_mutation_executor_shell,
    )

    result = preview_runtime_activation_queue_mutation_executor_shell({})

    assert result["executor_shell_ready"] is True
    assert result["mutation_executor_available"] is False
    assert result["mutation_execution_started"] is False
    assert result["mutation_execution_completed"] is False
    assert result["queue_mutation_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_queue_mutation_executor_shell_keeps_writes_transactions_and_storage_disabled():
    from core.runtime.runtime_activation_queue_mutation_executor_shell import (
        preview_runtime_activation_queue_mutation_executor_shell,
    )

    result = preview_runtime_activation_queue_mutation_executor_shell({})

    assert result["queue_write_allowed"] is False
    assert result["storage_call_allowed"] is False
    assert result["transaction_begin_allowed"] is False
    assert result["transaction_commit_allowed"] is False


def test_queue_mutation_executor_shell_preserves_final_gate_metadata():
    from core.runtime.runtime_activation_queue_mutation_executor_shell import (
        preview_runtime_activation_queue_mutation_executor_shell,
    )

    final_gate = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "final_gate_status": "disabled",
        "final_gate_reason": "queue_mutation_final_gate_disabled",
        "final_gate_ready": True,
        "safety_check_passed": True,
        "mutation_execution_authorized": False,
        "dry_run_snapshot": {
            "dry_run_status": "disabled",
            "authorization_snapshot": {"mutation_authorized": False},
        },
        "final_mutation_readiness_preview": {
            "safety_check_passed": True,
            "execution_authorized": False,
        },
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "final_gate_status": "disabled",
        "final_gate_reason": "queue_mutation_final_gate_disabled",
        "final_gate_ready": True,
        "safety_check_passed": True,
        "mutation_execution_authorized": False,
        "dry_run_snapshot": {
            "dry_run_status": "disabled",
            "authorization_snapshot": {"mutation_authorized": False},
        },
        "final_mutation_readiness_preview": {
            "safety_check_passed": True,
            "execution_authorized": False,
        },
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_queue_mutation_executor_shell(final_gate)

    assert final_gate == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == [
        "dry_run_snapshot",
        "extra",
        "final_gate_ready",
        "final_gate_reason",
        "final_gate_status",
        "final_mutation_readiness_preview",
        "identity_snapshot",
        "lineage_snapshot",
        "mutation_execution_authorized",
        "safety_check_passed",
    ]
    assert result["identity_snapshot"] == {
        "task_id": "task-1",
        "task_name": "Preview",
    }
    assert result["lineage_snapshot"] == {
        "lineage_id": "lineage-1",
        "trace_id": "trace-1",
    }
    assert result["final_gate_snapshot"] == {
        "final_gate_status": "disabled",
        "final_gate_reason": "queue_mutation_final_gate_disabled",
        "final_gate_ready": True,
        "safety_check_passed": True,
        "mutation_execution_authorized": False,
        "dry_run_snapshot": {
            "authorization_snapshot": {"mutation_authorized": False},
            "dry_run_status": "disabled",
        },
        "final_mutation_readiness_preview": {
            "execution_authorized": False,
            "safety_check_passed": True,
        },
    }


def test_queue_mutation_executor_shell_prepares_future_shell_metadata():
    from core.runtime.runtime_activation_queue_mutation_executor_shell import (
        preview_runtime_activation_queue_mutation_executor_shell,
    )

    result = preview_runtime_activation_queue_mutation_executor_shell({})

    assert result["future_executor_shell_preview"] == {
        "executor_layer": "runtime_queue_mutation",
        "executor_available": False,
        "execution_start_enabled": False,
        "execution_completion_enabled": False,
        "queue_write_enabled": False,
        "runtime_write_enabled": False,
    }


def test_queue_mutation_executor_shell_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_queue_mutation_executor_shell import (
        preview_runtime_activation_queue_mutation_executor_shell,
    )

    result = preview_runtime_activation_queue_mutation_executor_shell({})

    assert result["scheduler_call_allowed"] is False
    assert result["executor_runtime_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False


def test_queue_mutation_executor_shell_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_queue_mutation_executor_shell import (
        preview_runtime_activation_queue_mutation_executor_shell,
    )

    none_result = preview_runtime_activation_queue_mutation_executor_shell(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["mutation_executor_available"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_queue_mutation_executor_shell(malformed)
        assert result["mutation_executor_available"] is False
        assert result["mutation_execution_started"] is False
        assert result["mutation_execution_completed"] is False
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
    assert not any("storage" in module.lower() for module in imported_modules)
    assert not any("sqlite" in module.lower() for module in imported_modules)
    assert not any("database" in module.lower() for module in imported_modules)
    assert not any("scheduler" in module.lower() for module in imported_modules)
    assert not any("executor" in module.lower() for module in imported_modules)
    assert not any("subprocess" in module.lower() for module in imported_modules)
    assert not any("tool" in module.lower() for module in imported_modules)


def test_docs_explain_disabled_mutation_executor_shell():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "must not perform mutation",
        "Queue writes are forbidden",
        "Queue mutation is forbidden",
        "Storage calls are forbidden",
        "Transaction begin is forbidden",
        "Transaction commit is forbidden",
        "Scheduler runtime calls are forbidden",
        "Executor runtime calls are forbidden",
        "Tool execution is forbidden",
        "GO only for disabled queue mutation executor shell preview",
    ):
        assert phrase in text


def test_package_sequence_records_937_944():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 937-944" in text
    assert "Runtime Queue Mutation Executor Shell (Disabled)" in text
