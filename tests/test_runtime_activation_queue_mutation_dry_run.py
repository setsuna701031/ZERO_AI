import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_queue_mutation_dry_run.py"
DOC = ROOT / "docs/runtime_activation_queue_mutation_dry_run.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_queue_mutation_dry_run_imports_and_public_api_exists():
    from core.runtime import runtime_activation_queue_mutation_dry_run

    assert hasattr(
        runtime_activation_queue_mutation_dry_run,
        "preview_runtime_activation_queue_mutation_dry_run",
    )
    assert runtime_activation_queue_mutation_dry_run.__all__ == [
        "preview_runtime_activation_queue_mutation_dry_run"
    ]


def test_queue_mutation_dry_run_preview_is_deterministic():
    from core.runtime.runtime_activation_queue_mutation_dry_run import (
        preview_runtime_activation_queue_mutation_dry_run,
    )

    audit = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
        "audit_status": "disabled",
        "audit_reason": "queue_mutation_audit_disabled",
        "authorization_snapshot": {"mutation_authorized": False},
    }

    first = preview_runtime_activation_queue_mutation_dry_run(audit)
    second = preview_runtime_activation_queue_mutation_dry_run(audit)

    assert first == second
    assert first["mode"] == "queue_mutation_dry_run_preview"
    assert first["dry_run_status"] == "disabled"
    assert first["dry_run_reason"] == "queue_mutation_dry_run_disabled"
    assert first["result"] == "blocked"


def test_queue_mutation_dry_run_keeps_mutation_execution_disabled():
    from core.runtime.runtime_activation_queue_mutation_dry_run import (
        preview_runtime_activation_queue_mutation_dry_run,
    )

    result = preview_runtime_activation_queue_mutation_dry_run({})

    assert result["dry_run_ready"] is True
    assert result["mutation_plan_created"] is False
    assert result["mutation_execution_allowed"] is False
    assert result["queue_mutation_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["transaction_execution_allowed"] is False
    assert result["queue_write_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_queue_mutation_dry_run_keeps_persistence_disabled():
    from core.runtime.runtime_activation_queue_mutation_dry_run import (
        preview_runtime_activation_queue_mutation_dry_run,
    )

    result = preview_runtime_activation_queue_mutation_dry_run({})

    assert result["storage_call_allowed"] is False
    assert result["persistence_allowed"] is False
    assert result["mutation_plan_preview"]["persistence_enabled"] is False
    assert result["mutation_plan_preview"]["queue_write_enabled"] is False
    assert result["mutation_plan_preview"]["runtime_write_enabled"] is False


def test_queue_mutation_dry_run_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_queue_mutation_dry_run import (
        preview_runtime_activation_queue_mutation_dry_run,
    )

    result = preview_runtime_activation_queue_mutation_dry_run({})

    assert result["scheduler_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False


def test_queue_mutation_dry_run_snapshots_metadata_without_mutating_input():
    from core.runtime.runtime_activation_queue_mutation_dry_run import (
        preview_runtime_activation_queue_mutation_dry_run,
    )

    audit = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "audit_status": "disabled",
        "audit_reason": "queue_mutation_audit_disabled",
        "audit_record_created": False,
        "audit_persistence_allowed": False,
        "mutation_audited": False,
        "authorization_snapshot": {
            "authority_status": "disabled",
            "mutation_authorized": False,
        },
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "audit_status": "disabled",
        "audit_reason": "queue_mutation_audit_disabled",
        "audit_record_created": False,
        "audit_persistence_allowed": False,
        "mutation_audited": False,
        "authorization_snapshot": {
            "authority_status": "disabled",
            "mutation_authorized": False,
        },
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_queue_mutation_dry_run(audit)

    assert audit == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == [
        "audit_persistence_allowed",
        "audit_reason",
        "audit_record_created",
        "audit_status",
        "authorization_snapshot",
        "extra",
        "identity_snapshot",
        "lineage_snapshot",
        "mutation_audited",
    ]
    assert result["identity_snapshot"] == {
        "task_id": "task-1",
        "task_name": "Preview",
    }
    assert result["lineage_snapshot"] == {
        "lineage_id": "lineage-1",
        "trace_id": "trace-1",
    }
    assert result["audit_snapshot"] == {
        "audit_status": "disabled",
        "audit_reason": "queue_mutation_audit_disabled",
        "audit_record_created": False,
        "audit_persistence_allowed": False,
        "mutation_audited": False,
        "authorization_snapshot": {
            "authority_status": "disabled",
            "mutation_authorized": False,
        },
    }


def test_queue_mutation_dry_run_prepares_future_plan_preview():
    from core.runtime.runtime_activation_queue_mutation_dry_run import (
        preview_runtime_activation_queue_mutation_dry_run,
    )

    result = preview_runtime_activation_queue_mutation_dry_run({})

    assert result["mutation_plan_preview"] == {
        "plan_type": "runtime_queue_mutation",
        "plan_created": False,
        "execution_enabled": False,
        "persistence_enabled": False,
        "queue_write_enabled": False,
        "runtime_write_enabled": False,
    }


def test_queue_mutation_dry_run_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_queue_mutation_dry_run import (
        preview_runtime_activation_queue_mutation_dry_run,
    )

    none_result = preview_runtime_activation_queue_mutation_dry_run(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["mutation_plan_created"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_queue_mutation_dry_run(malformed)
        assert result["mutation_plan_created"] is False
        assert result["mutation_execution_allowed"] is False
        assert result["queue_mutation_allowed"] is False
        assert result["runtime_mutation_allowed"] is False
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


def test_docs_explain_disabled_mutation_dry_run_planner():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "must not mutate queue or runtime state",
        "Queue writes are forbidden",
        "Transaction execution is forbidden",
        "Storage calls are forbidden",
        "Scheduler imports and calls are forbidden",
        "Executor imports and calls are forbidden",
        "Tool execution is forbidden",
        "Repo mutation is forbidden",
        "GO only for disabled queue mutation dry-run preview",
    ):
        assert phrase in text


def test_package_sequence_records_921_928():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 921-928" in text
    assert "Runtime Queue Mutation Dry-Run Planner (Disabled)" in text
