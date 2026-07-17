import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_queue_mutation_authorization.py"
DOC = ROOT / "docs/runtime_activation_queue_mutation_authorization.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_queue_mutation_authorization_imports_and_public_api_exists():
    from core.runtime import runtime_activation_queue_mutation_authorization

    assert hasattr(
        runtime_activation_queue_mutation_authorization,
        "preview_runtime_activation_queue_mutation_authorization",
    )
    assert runtime_activation_queue_mutation_authorization.__all__ == [
        "preview_runtime_activation_queue_mutation_authorization"
    ]


def test_queue_mutation_authorization_preview_is_deterministic():
    from core.runtime.runtime_activation_queue_mutation_authorization import (
        preview_runtime_activation_queue_mutation_authorization,
    )

    transaction = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
    }

    first = preview_runtime_activation_queue_mutation_authorization(transaction)
    second = preview_runtime_activation_queue_mutation_authorization(transaction)

    assert first == second
    assert first["mode"] == "queue_mutation_authorization_preview"
    assert first["authority_status"] == "disabled"
    assert first["authority_reason"] == "queue_mutation_authorization_disabled"
    assert first["result"] == "blocked"


def test_queue_mutation_authorization_keeps_mutation_blocked():
    from core.runtime.runtime_activation_queue_mutation_authorization import (
        preview_runtime_activation_queue_mutation_authorization,
    )

    result = preview_runtime_activation_queue_mutation_authorization({})

    assert result["mutation_authorization_ready"] is True
    assert result["mutation_authorized"] is False
    assert result["queue_mutation_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["transaction_execution_allowed"] is False
    assert result["queue_write_allowed"] is False
    assert result["storage_call_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_queue_mutation_authorization_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_queue_mutation_authorization import (
        preview_runtime_activation_queue_mutation_authorization,
    )

    result = preview_runtime_activation_queue_mutation_authorization({})

    assert result["scheduler_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False


def test_queue_mutation_authorization_snapshots_identity_and_lineage():
    from core.runtime.runtime_activation_queue_mutation_authorization import (
        preview_runtime_activation_queue_mutation_authorization,
    )

    transaction = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_queue_mutation_authorization(transaction)

    assert transaction == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == ["extra", "identity_snapshot", "lineage_snapshot"]
    assert result["identity_snapshot"] == {
        "task_id": "task-1",
        "task_name": "Preview",
    }
    assert result["lineage_snapshot"] == {
        "lineage_id": "lineage-1",
        "trace_id": "trace-1",
    }
    assert result["future_mutation_authorization_preview"] == {
        "authorization_layer": "runtime_queue_mutation",
        "authority_available": False,
        "mutation_authorized": False,
        "queue_write_enabled": False,
        "runtime_write_enabled": False,
    }


def test_queue_mutation_authorization_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_queue_mutation_authorization import (
        preview_runtime_activation_queue_mutation_authorization,
    )

    none_result = preview_runtime_activation_queue_mutation_authorization(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["mutation_authorized"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_queue_mutation_authorization(malformed)
        assert result["mutation_authorized"] is False
        assert result["queue_mutation_allowed"] is False
        assert result["runtime_mutation_allowed"] is False
        assert result["transaction_execution_allowed"] is False


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


def test_docs_explain_disabled_mutation_authorization():
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
        "Queue mutation is forbidden",
        "Repo mutation is forbidden",
        "GO only for disabled queue mutation authorization preview",
    ):
        assert phrase in text


def test_package_sequence_records_905_912():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 905-912" in text
    assert "Runtime Queue Mutation Authorization Gate (Disabled)" in text
