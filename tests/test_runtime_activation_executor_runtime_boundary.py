import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_executor_runtime_boundary.py"
DOC = ROOT / "docs/runtime_activation_executor_runtime_boundary.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_executor_runtime_boundary_imports_and_public_api_exists():
    from core.runtime import runtime_activation_executor_runtime_boundary

    assert hasattr(
        runtime_activation_executor_runtime_boundary,
        "preview_runtime_activation_executor_runtime_boundary",
    )
    assert runtime_activation_executor_runtime_boundary.__all__ == [
        "preview_runtime_activation_executor_runtime_boundary"
    ]


def test_executor_runtime_boundary_preview_is_deterministic():
    from core.runtime.runtime_activation_executor_runtime_boundary import (
        preview_runtime_activation_executor_runtime_boundary,
    )

    admission = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
        "admission_status": "disabled",
        "admission_reason": "executor_admission_disabled",
        "executor_admission_granted": False,
    }

    first = preview_runtime_activation_executor_runtime_boundary(admission)
    second = preview_runtime_activation_executor_runtime_boundary(admission)

    assert first == second
    assert first["mode"] == "executor_runtime_boundary_preview"
    assert first["runtime_status"] == "disabled"
    assert first["runtime_reason"] == "executor_runtime_disabled"
    assert first["result"] == "blocked"


def test_executor_runtime_boundary_remains_disabled():
    from core.runtime.runtime_activation_executor_runtime_boundary import (
        preview_runtime_activation_executor_runtime_boundary,
    )

    result = preview_runtime_activation_executor_runtime_boundary({})

    assert result["executor_runtime_boundary_ready"] is True
    assert result["executor_runtime_available"] is False
    assert result["execution_started"] is False
    assert result["execution_completed"] is False
    assert result["execution_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["repo_mutation_allowed"] is False


def test_executor_runtime_boundary_prepares_future_runtime_metadata():
    from core.runtime.runtime_activation_executor_runtime_boundary import (
        preview_runtime_activation_executor_runtime_boundary,
    )

    result = preview_runtime_activation_executor_runtime_boundary({})

    assert result["executor_runtime_preview"] == {
        "runtime_layer": "runtime_executor_boundary",
        "executor_runtime_available": False,
        "runtime_started": False,
        "runtime_completed": False,
        "execution_enabled": False,
        "tool_execution_enabled": False,
    }


def test_executor_runtime_boundary_preserves_executor_admission_metadata():
    from core.runtime.runtime_activation_executor_runtime_boundary import (
        preview_runtime_activation_executor_runtime_boundary,
    )

    admission = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "admission_status": "disabled",
        "admission_reason": "executor_admission_disabled",
        "executor_admission_ready": True,
        "executor_available": False,
        "executor_admission_granted": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "runtime_mutation_allowed": False,
        "scheduler_dispatch_snapshot": {
            "dispatch_status": "disabled",
            "dispatch_created": False,
        },
        "executor_admission_preview": {
            "admission_layer": "runtime_executor_admission",
            "admission_granted": False,
        },
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "admission_status": "disabled",
        "admission_reason": "executor_admission_disabled",
        "executor_admission_ready": True,
        "executor_available": False,
        "executor_admission_granted": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "runtime_mutation_allowed": False,
        "scheduler_dispatch_snapshot": {
            "dispatch_status": "disabled",
            "dispatch_created": False,
        },
        "executor_admission_preview": {
            "admission_layer": "runtime_executor_admission",
            "admission_granted": False,
        },
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_executor_runtime_boundary(admission)

    assert admission == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == [
        "admission_reason",
        "admission_status",
        "execution_allowed",
        "executor_admission_granted",
        "executor_admission_preview",
        "executor_admission_ready",
        "executor_available",
        "extra",
        "identity_snapshot",
        "lineage_snapshot",
        "runtime_mutation_allowed",
        "scheduler_dispatch_snapshot",
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
    assert result["executor_admission_snapshot"] == {
        "admission_status": "disabled",
        "admission_reason": "executor_admission_disabled",
        "executor_admission_ready": True,
        "executor_available": False,
        "executor_admission_granted": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "runtime_mutation_allowed": False,
        "scheduler_dispatch_snapshot": {
            "dispatch_created": False,
            "dispatch_status": "disabled",
        },
        "executor_admission_preview": {
            "admission_granted": False,
            "admission_layer": "runtime_executor_admission",
        },
    }


def test_executor_runtime_boundary_has_no_io_or_mutation_flags():
    from core.runtime.runtime_activation_executor_runtime_boundary import (
        preview_runtime_activation_executor_runtime_boundary,
    )

    result = preview_runtime_activation_executor_runtime_boundary({})

    assert result["queue_read_allowed"] is False
    assert result["queue_write_allowed"] is False
    assert result["filesystem_io_allowed"] is False
    assert result["database_io_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_executor_runtime_boundary_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_executor_runtime_boundary import (
        preview_runtime_activation_executor_runtime_boundary,
    )

    result = preview_runtime_activation_executor_runtime_boundary({})

    assert result["scheduler_runtime_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False


def test_executor_runtime_boundary_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_executor_runtime_boundary import (
        preview_runtime_activation_executor_runtime_boundary,
    )

    none_result = preview_runtime_activation_executor_runtime_boundary(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["executor_runtime_available"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_executor_runtime_boundary(malformed)
        assert result["executor_runtime_available"] is False
        assert result["execution_started"] is False
        assert result["execution_completed"] is False
        assert result["execution_allowed"] is False
        assert result["tool_execution_allowed"] is False
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


def test_docs_explain_disabled_executor_runtime_boundary():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "disabled executor runtime boundary",
        "Executor imports and calls are forbidden",
        "Tool calls are forbidden",
        "Subprocess use is forbidden",
        "Scheduler runtime calls are forbidden",
        "Queue reads are forbidden",
        "Queue writes are forbidden",
        "GO only for disabled executor runtime boundary preview",
    ):
        assert phrase in text


def test_package_sequence_records_1001_1008():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 1001-1008" in text
    assert "Runtime Executor Runtime Boundary (Disabled)" in text
