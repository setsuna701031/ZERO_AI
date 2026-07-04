import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_executor_tool_boundary.py"
DOC = ROOT / "docs/runtime_activation_executor_tool_boundary.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_executor_tool_boundary_imports_and_public_api_exists():
    from core.runtime import runtime_activation_executor_tool_boundary

    assert hasattr(
        runtime_activation_executor_tool_boundary,
        "preview_runtime_activation_executor_tool_boundary",
    )
    assert runtime_activation_executor_tool_boundary.__all__ == [
        "preview_runtime_activation_executor_tool_boundary"
    ]


def test_executor_tool_boundary_preview_is_deterministic():
    from core.runtime.runtime_activation_executor_tool_boundary import (
        preview_runtime_activation_executor_tool_boundary,
    )

    runtime = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
        "runtime_status": "disabled",
        "runtime_reason": "executor_runtime_disabled",
        "executor_runtime_available": False,
    }

    first = preview_runtime_activation_executor_tool_boundary(runtime)
    second = preview_runtime_activation_executor_tool_boundary(runtime)

    assert first == second
    assert first["mode"] == "executor_tool_boundary_preview"
    assert first["tool_boundary_status"] == "disabled"
    assert first["tool_boundary_reason"] == "executor_tool_boundary_disabled"
    assert first["result"] == "blocked"


def test_executor_tool_boundary_remains_disabled():
    from core.runtime.runtime_activation_executor_tool_boundary import (
        preview_runtime_activation_executor_tool_boundary,
    )

    result = preview_runtime_activation_executor_tool_boundary({})

    assert result["tool_boundary_ready"] is True
    assert result["tool_runtime_available"] is False
    assert result["tool_execution_allowed"] is False
    assert result["tool_call_started"] is False
    assert result["tool_call_completed"] is False
    assert result["execution_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["repo_mutation_allowed"] is False


def test_executor_tool_boundary_prepares_future_tool_metadata():
    from core.runtime.runtime_activation_executor_tool_boundary import (
        preview_runtime_activation_executor_tool_boundary,
    )

    result = preview_runtime_activation_executor_tool_boundary({})

    assert result["executor_tool_preview"] == {
        "tool_layer": "runtime_executor_tool_boundary",
        "tool_runtime_available": False,
        "tool_call_enabled": False,
        "tool_call_started": False,
        "tool_call_completed": False,
        "execution_enabled": False,
    }


def test_executor_tool_boundary_preserves_executor_runtime_metadata():
    from core.runtime.runtime_activation_executor_tool_boundary import (
        preview_runtime_activation_executor_tool_boundary,
    )

    runtime = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "runtime_status": "disabled",
        "runtime_reason": "executor_runtime_disabled",
        "executor_runtime_boundary_ready": True,
        "executor_runtime_available": False,
        "execution_started": False,
        "execution_completed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "executor_admission_snapshot": {
            "admission_status": "disabled",
            "executor_admission_granted": False,
        },
        "executor_runtime_preview": {
            "runtime_layer": "runtime_executor_boundary",
            "executor_runtime_available": False,
        },
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "runtime_status": "disabled",
        "runtime_reason": "executor_runtime_disabled",
        "executor_runtime_boundary_ready": True,
        "executor_runtime_available": False,
        "execution_started": False,
        "execution_completed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "executor_admission_snapshot": {
            "admission_status": "disabled",
            "executor_admission_granted": False,
        },
        "executor_runtime_preview": {
            "runtime_layer": "runtime_executor_boundary",
            "executor_runtime_available": False,
        },
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_executor_tool_boundary(runtime)

    assert runtime == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == [
        "execution_allowed",
        "execution_completed",
        "execution_started",
        "executor_admission_snapshot",
        "executor_runtime_available",
        "executor_runtime_boundary_ready",
        "executor_runtime_preview",
        "extra",
        "identity_snapshot",
        "lineage_snapshot",
        "repo_mutation_allowed",
        "runtime_mutation_allowed",
        "runtime_reason",
        "runtime_status",
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
    assert result["executor_runtime_snapshot"] == {
        "runtime_status": "disabled",
        "runtime_reason": "executor_runtime_disabled",
        "executor_runtime_boundary_ready": True,
        "executor_runtime_available": False,
        "execution_started": False,
        "execution_completed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "executor_admission_snapshot": {
            "admission_status": "disabled",
            "executor_admission_granted": False,
        },
        "executor_runtime_preview": {
            "executor_runtime_available": False,
            "runtime_layer": "runtime_executor_boundary",
        },
    }


def test_executor_tool_boundary_has_no_io_or_mutation_flags():
    from core.runtime.runtime_activation_executor_tool_boundary import (
        preview_runtime_activation_executor_tool_boundary,
    )

    result = preview_runtime_activation_executor_tool_boundary({})

    assert result["queue_read_allowed"] is False
    assert result["queue_write_allowed"] is False
    assert result["filesystem_io_allowed"] is False
    assert result["database_io_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_executor_tool_boundary_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_executor_tool_boundary import (
        preview_runtime_activation_executor_tool_boundary,
    )

    result = preview_runtime_activation_executor_tool_boundary({})

    assert result["scheduler_runtime_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_import_allowed"] is False
    assert result["tool_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False


def test_executor_tool_boundary_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_executor_tool_boundary import (
        preview_runtime_activation_executor_tool_boundary,
    )

    none_result = preview_runtime_activation_executor_tool_boundary(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["tool_runtime_available"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_executor_tool_boundary(malformed)
        assert result["tool_runtime_available"] is False
        assert result["tool_execution_allowed"] is False
        assert result["tool_call_started"] is False
        assert result["tool_call_completed"] is False
        assert result["execution_allowed"] is False
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


def test_docs_explain_disabled_executor_tool_boundary():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "disabled executor tool boundary",
        "Tool imports and calls are forbidden",
        "Executor imports and calls are forbidden",
        "Subprocess use is forbidden",
        "Scheduler runtime calls are forbidden",
        "Queue reads are forbidden",
        "Queue writes are forbidden",
        "GO only for disabled executor tool boundary preview",
    ):
        assert phrase in text


def test_package_sequence_records_1009_1016():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 1009-1016" in text
    assert "Runtime Executor Tool Boundary (Disabled)" in text
