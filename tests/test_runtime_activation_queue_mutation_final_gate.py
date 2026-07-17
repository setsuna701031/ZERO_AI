import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_queue_mutation_final_gate.py"
DOC = ROOT / "docs/runtime_activation_queue_mutation_final_gate.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_queue_mutation_final_gate_imports_and_public_api_exists():
    from core.runtime import runtime_activation_queue_mutation_final_gate

    assert hasattr(
        runtime_activation_queue_mutation_final_gate,
        "preview_runtime_activation_queue_mutation_final_gate",
    )
    assert runtime_activation_queue_mutation_final_gate.__all__ == [
        "preview_runtime_activation_queue_mutation_final_gate"
    ]


def test_queue_mutation_final_gate_output_is_deterministic():
    from core.runtime.runtime_activation_queue_mutation_final_gate import (
        preview_runtime_activation_queue_mutation_final_gate,
    )

    dry_run = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
        "dry_run_status": "disabled",
        "dry_run_reason": "queue_mutation_dry_run_disabled",
        "audit_snapshot": {
            "audit_status": "disabled",
            "authorization_snapshot": {"mutation_authorized": False},
        },
    }

    first = preview_runtime_activation_queue_mutation_final_gate(dry_run)
    second = preview_runtime_activation_queue_mutation_final_gate(dry_run)

    assert first == second
    assert first["mode"] == "queue_mutation_final_gate_preview"
    assert first["final_gate_status"] == "disabled"
    assert first["final_gate_reason"] == "queue_mutation_final_gate_disabled"
    assert first["result"] == "blocked"


def test_queue_mutation_final_gate_keeps_mutation_blocked():
    from core.runtime.runtime_activation_queue_mutation_final_gate import (
        preview_runtime_activation_queue_mutation_final_gate,
    )

    result = preview_runtime_activation_queue_mutation_final_gate({})

    assert result["final_gate_ready"] is True
    assert result["mutation_execution_authorized"] is False
    assert result["queue_mutation_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["queue_write_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_queue_mutation_final_gate_keeps_transactions_and_storage_disabled():
    from core.runtime.runtime_activation_queue_mutation_final_gate import (
        preview_runtime_activation_queue_mutation_final_gate,
    )

    result = preview_runtime_activation_queue_mutation_final_gate({})

    assert result["storage_call_allowed"] is False
    assert result["transaction_begin_allowed"] is False
    assert result["transaction_commit_allowed"] is False


def test_queue_mutation_final_gate_preserves_authorization_and_audit_metadata():
    from core.runtime.runtime_activation_queue_mutation_final_gate import (
        preview_runtime_activation_queue_mutation_final_gate,
    )

    dry_run = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "dry_run_status": "disabled",
        "dry_run_reason": "queue_mutation_dry_run_disabled",
        "mutation_plan_created": False,
        "mutation_execution_allowed": False,
        "audit_snapshot": {
            "audit_status": "disabled",
            "audit_reason": "queue_mutation_audit_disabled",
            "authorization_snapshot": {
                "authority_status": "disabled",
                "mutation_authorized": False,
            },
        },
        "mutation_plan_preview": {
            "plan_type": "runtime_queue_mutation",
            "execution_enabled": False,
        },
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "dry_run_status": "disabled",
        "dry_run_reason": "queue_mutation_dry_run_disabled",
        "mutation_plan_created": False,
        "mutation_execution_allowed": False,
        "audit_snapshot": {
            "audit_status": "disabled",
            "audit_reason": "queue_mutation_audit_disabled",
            "authorization_snapshot": {
                "authority_status": "disabled",
                "mutation_authorized": False,
            },
        },
        "mutation_plan_preview": {
            "plan_type": "runtime_queue_mutation",
            "execution_enabled": False,
        },
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_queue_mutation_final_gate(dry_run)

    assert dry_run == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == [
        "audit_snapshot",
        "dry_run_reason",
        "dry_run_status",
        "extra",
        "identity_snapshot",
        "lineage_snapshot",
        "mutation_execution_allowed",
        "mutation_plan_created",
        "mutation_plan_preview",
    ]
    assert result["identity_snapshot"] == {
        "task_id": "task-1",
        "task_name": "Preview",
    }
    assert result["lineage_snapshot"] == {
        "lineage_id": "lineage-1",
        "trace_id": "trace-1",
    }
    assert result["safety_check_passed"] is True
    assert result["dry_run_snapshot"] == {
        "dry_run_status": "disabled",
        "dry_run_reason": "queue_mutation_dry_run_disabled",
        "mutation_plan_created": False,
        "mutation_execution_allowed": False,
        "audit_snapshot": {
            "audit_reason": "queue_mutation_audit_disabled",
            "audit_status": "disabled",
            "authorization_snapshot": {
                "authority_status": "disabled",
                "mutation_authorized": False,
            },
        },
        "authorization_snapshot": {
            "authority_status": "disabled",
            "mutation_authorized": False,
        },
        "mutation_plan_preview": {
            "execution_enabled": False,
            "plan_type": "runtime_queue_mutation",
        },
    }


def test_queue_mutation_final_gate_prepares_readiness_metadata():
    from core.runtime.runtime_activation_queue_mutation_final_gate import (
        preview_runtime_activation_queue_mutation_final_gate,
    )

    dry_run = {
        "audit_snapshot": {
            "authorization_snapshot": {"mutation_authorized": False},
        },
    }

    result = preview_runtime_activation_queue_mutation_final_gate(dry_run)

    assert result["final_mutation_readiness_preview"] == {
        "readiness_layer": "runtime_queue_mutation_final_gate",
        "authorization_chain_present": True,
        "audit_chain_present": True,
        "safety_check_passed": True,
        "execution_authorized": False,
    }
    assert result["mutation_execution_authorized"] is False


def test_queue_mutation_final_gate_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_queue_mutation_final_gate import (
        preview_runtime_activation_queue_mutation_final_gate,
    )

    result = preview_runtime_activation_queue_mutation_final_gate({})

    assert result["scheduler_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False


def test_queue_mutation_final_gate_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_queue_mutation_final_gate import (
        preview_runtime_activation_queue_mutation_final_gate,
    )

    none_result = preview_runtime_activation_queue_mutation_final_gate(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["safety_check_passed"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_queue_mutation_final_gate(malformed)
        assert result["safety_check_passed"] is False
        assert result["mutation_execution_authorized"] is False
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


def test_docs_explain_disabled_mutation_final_gate():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "must not execute mutation",
        "Queue mutation is forbidden",
        "Queue writes are forbidden",
        "Storage calls are forbidden",
        "Transaction begin is forbidden",
        "Transaction commit is forbidden",
        "Scheduler imports and calls are forbidden",
        "Executor imports and calls are forbidden",
        "Tool execution is forbidden",
        "GO only for disabled queue mutation final safety gate preview",
    ):
        assert phrase in text


def test_package_sequence_records_929_936():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 929-936" in text
    assert "Runtime Queue Mutation Final Safety Gate (Disabled)" in text
