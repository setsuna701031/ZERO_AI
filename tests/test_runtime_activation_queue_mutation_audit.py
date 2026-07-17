import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_queue_mutation_audit.py"
DOC = ROOT / "docs/runtime_activation_queue_mutation_audit.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_queue_mutation_audit_imports_and_public_api_exists():
    from core.runtime import runtime_activation_queue_mutation_audit

    assert hasattr(
        runtime_activation_queue_mutation_audit,
        "preview_runtime_activation_queue_mutation_audit",
    )
    assert runtime_activation_queue_mutation_audit.__all__ == [
        "preview_runtime_activation_queue_mutation_audit"
    ]


def test_queue_mutation_audit_preview_is_deterministic():
    from core.runtime.runtime_activation_queue_mutation_audit import (
        preview_runtime_activation_queue_mutation_audit,
    )

    authorization = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
        "authority_status": "disabled",
        "authority_reason": "queue_mutation_authorization_disabled",
        "mutation_authorized": False,
    }

    first = preview_runtime_activation_queue_mutation_audit(authorization)
    second = preview_runtime_activation_queue_mutation_audit(authorization)

    assert first == second
    assert first["mode"] == "queue_mutation_audit_preview"
    assert first["audit_status"] == "disabled"
    assert first["audit_reason"] == "queue_mutation_audit_disabled"
    assert first["result"] == "blocked"


def test_queue_mutation_audit_keeps_audit_persistence_disabled():
    from core.runtime.runtime_activation_queue_mutation_audit import (
        preview_runtime_activation_queue_mutation_audit,
    )

    result = preview_runtime_activation_queue_mutation_audit({})

    assert result["audit_boundary_ready"] is True
    assert result["audit_record_created"] is False
    assert result["audit_persistence_allowed"] is False
    assert result["mutation_audited"] is False
    assert result["audit_file_write_allowed"] is False
    assert result["database_write_allowed"] is False
    assert result["storage_call_allowed"] is False


def test_queue_mutation_audit_keeps_mutation_path_blocked():
    from core.runtime.runtime_activation_queue_mutation_audit import (
        preview_runtime_activation_queue_mutation_audit,
    )

    result = preview_runtime_activation_queue_mutation_audit({})

    assert result["queue_mutation_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_queue_mutation_audit_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_queue_mutation_audit import (
        preview_runtime_activation_queue_mutation_audit,
    )

    result = preview_runtime_activation_queue_mutation_audit({})

    assert result["scheduler_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False


def test_queue_mutation_audit_snapshots_metadata_without_mutating_input():
    from core.runtime.runtime_activation_queue_mutation_audit import (
        preview_runtime_activation_queue_mutation_audit,
    )

    authorization = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "authority_status": "disabled",
        "authority_reason": "queue_mutation_authorization_disabled",
        "mutation_authorized": False,
        "queue_mutation_allowed": False,
        "runtime_mutation_allowed": False,
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "authority_status": "disabled",
        "authority_reason": "queue_mutation_authorization_disabled",
        "mutation_authorized": False,
        "queue_mutation_allowed": False,
        "runtime_mutation_allowed": False,
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_queue_mutation_audit(authorization)

    assert authorization == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == [
        "authority_reason",
        "authority_status",
        "extra",
        "identity_snapshot",
        "lineage_snapshot",
        "mutation_authorized",
        "queue_mutation_allowed",
        "runtime_mutation_allowed",
    ]
    assert result["identity_snapshot"] == {
        "task_id": "task-1",
        "task_name": "Preview",
    }
    assert result["lineage_snapshot"] == {
        "lineage_id": "lineage-1",
        "trace_id": "trace-1",
    }
    assert result["authorization_snapshot"] == {
        "authority_status": "disabled",
        "authority_reason": "queue_mutation_authorization_disabled",
        "mutation_authorized": False,
        "queue_mutation_allowed": False,
        "runtime_mutation_allowed": False,
    }


def test_queue_mutation_audit_prepares_future_evidence_metadata():
    from core.runtime.runtime_activation_queue_mutation_audit import (
        preview_runtime_activation_queue_mutation_audit,
    )

    result = preview_runtime_activation_queue_mutation_audit({})

    assert result["future_audit_evidence_preview"] == {
        "evidence_layer": "runtime_queue_mutation",
        "audit_record_available": False,
        "audit_record_created": False,
        "audit_persistence_enabled": False,
        "mutation_audited": False,
    }


def test_queue_mutation_audit_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_queue_mutation_audit import (
        preview_runtime_activation_queue_mutation_audit,
    )

    none_result = preview_runtime_activation_queue_mutation_audit(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["audit_record_created"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_queue_mutation_audit(malformed)
        assert result["audit_record_created"] is False
        assert result["audit_persistence_allowed"] is False
        assert result["mutation_audited"] is False
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


def test_docs_explain_disabled_mutation_audit_boundary():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "must not mutate queue or runtime state",
        "Audit file writes are forbidden",
        "Database writes are forbidden",
        "Queue mutation is forbidden",
        "Storage calls are forbidden",
        "Scheduler imports and calls are forbidden",
        "Executor imports and calls are forbidden",
        "Tool execution is forbidden",
        "GO only for disabled queue mutation audit preview",
    ):
        assert phrase in text


def test_package_sequence_records_913_920():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 913-920" in text
    assert "Runtime Queue Mutation Audit Boundary (Disabled)" in text
