import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_executor_execution_plan.py"
DOC = ROOT / "docs/runtime_activation_executor_execution_plan.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_executor_execution_plan_imports_and_public_api_exists():
    from core.runtime import runtime_activation_executor_execution_plan

    assert hasattr(
        runtime_activation_executor_execution_plan,
        "preview_runtime_activation_executor_execution_plan",
    )
    assert runtime_activation_executor_execution_plan.__all__ == [
        "preview_runtime_activation_executor_execution_plan"
    ]


def test_executor_execution_plan_preview_is_deterministic():
    from core.runtime.runtime_activation_executor_execution_plan import (
        preview_runtime_activation_executor_execution_plan,
    )

    tool_boundary = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
        "tool_boundary_status": "disabled",
        "tool_boundary_reason": "executor_tool_boundary_disabled",
        "tool_runtime_available": False,
    }

    first = preview_runtime_activation_executor_execution_plan(tool_boundary)
    second = preview_runtime_activation_executor_execution_plan(tool_boundary)

    assert first == second
    assert first["mode"] == "executor_execution_plan_preview"
    assert first["execution_plan_status"] == "disabled"
    assert first["execution_plan_reason"] == "executor_execution_plan_disabled"
    assert first["result"] == "blocked"


def test_executor_execution_plan_remains_disabled():
    from core.runtime.runtime_activation_executor_execution_plan import (
        preview_runtime_activation_executor_execution_plan,
    )

    result = preview_runtime_activation_executor_execution_plan({})

    assert result["execution_plan_ready"] is True
    assert result["execution_plan_created"] is False
    assert result["execution_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["tool_call_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["repo_mutation_allowed"] is False


def test_executor_execution_plan_prepares_future_plan_metadata():
    from core.runtime.runtime_activation_executor_execution_plan import (
        preview_runtime_activation_executor_execution_plan,
    )

    result = preview_runtime_activation_executor_execution_plan({})

    assert result["execution_plan_preview"] == {
        "plan_layer": "runtime_executor_execution_plan",
        "execution_plan_available": False,
        "execution_plan_created": False,
        "execution_enabled": False,
        "tool_execution_enabled": False,
        "repo_mutation_enabled": False,
    }


def test_executor_execution_plan_preserves_executor_tool_metadata():
    from core.runtime.runtime_activation_executor_execution_plan import (
        preview_runtime_activation_executor_execution_plan,
    )

    tool_boundary = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "tool_boundary_status": "disabled",
        "tool_boundary_reason": "executor_tool_boundary_disabled",
        "tool_boundary_ready": True,
        "tool_runtime_available": False,
        "tool_execution_allowed": False,
        "tool_call_started": False,
        "tool_call_completed": False,
        "execution_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "executor_runtime_snapshot": {
            "runtime_status": "disabled",
            "executor_runtime_available": False,
        },
        "executor_tool_preview": {
            "tool_layer": "runtime_executor_tool_boundary",
            "tool_runtime_available": False,
        },
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "tool_boundary_status": "disabled",
        "tool_boundary_reason": "executor_tool_boundary_disabled",
        "tool_boundary_ready": True,
        "tool_runtime_available": False,
        "tool_execution_allowed": False,
        "tool_call_started": False,
        "tool_call_completed": False,
        "execution_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "executor_runtime_snapshot": {
            "runtime_status": "disabled",
            "executor_runtime_available": False,
        },
        "executor_tool_preview": {
            "tool_layer": "runtime_executor_tool_boundary",
            "tool_runtime_available": False,
        },
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_executor_execution_plan(tool_boundary)

    assert tool_boundary == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == [
        "execution_allowed",
        "executor_runtime_snapshot",
        "executor_tool_preview",
        "extra",
        "identity_snapshot",
        "lineage_snapshot",
        "repo_mutation_allowed",
        "runtime_mutation_allowed",
        "tool_boundary_ready",
        "tool_boundary_reason",
        "tool_boundary_status",
        "tool_call_completed",
        "tool_call_started",
        "tool_execution_allowed",
        "tool_runtime_available",
    ]
    assert result["identity_snapshot"] == {
        "task_id": "task-1",
        "task_name": "Preview",
    }
    assert result["lineage_snapshot"] == {
        "lineage_id": "lineage-1",
        "trace_id": "trace-1",
    }
    assert result["executor_tool_snapshot"] == {
        "tool_boundary_status": "disabled",
        "tool_boundary_reason": "executor_tool_boundary_disabled",
        "tool_boundary_ready": True,
        "tool_runtime_available": False,
        "tool_execution_allowed": False,
        "tool_call_started": False,
        "tool_call_completed": False,
        "execution_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "executor_runtime_snapshot": {
            "executor_runtime_available": False,
            "runtime_status": "disabled",
        },
        "executor_tool_preview": {
            "tool_layer": "runtime_executor_tool_boundary",
            "tool_runtime_available": False,
        },
    }


def test_executor_execution_plan_has_no_io_or_mutation_flags():
    from core.runtime.runtime_activation_executor_execution_plan import (
        preview_runtime_activation_executor_execution_plan,
    )

    result = preview_runtime_activation_executor_execution_plan({})

    assert result["queue_read_allowed"] is False
    assert result["queue_write_allowed"] is False
    assert result["filesystem_io_allowed"] is False
    assert result["database_io_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_executor_execution_plan_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_executor_execution_plan import (
        preview_runtime_activation_executor_execution_plan,
    )

    result = preview_runtime_activation_executor_execution_plan({})

    assert result["scheduler_runtime_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_import_allowed"] is False
    assert result["tool_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False


def test_executor_execution_plan_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_executor_execution_plan import (
        preview_runtime_activation_executor_execution_plan,
    )

    none_result = preview_runtime_activation_executor_execution_plan(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["execution_plan_created"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_executor_execution_plan(malformed)
        assert result["execution_plan_created"] is False
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


def test_docs_explain_disabled_executor_execution_plan():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "disabled executor execution plan boundary",
        "Tool imports and calls are forbidden",
        "Executor imports and calls are forbidden",
        "Subprocess use is forbidden",
        "Scheduler runtime calls are forbidden",
        "Queue reads are forbidden",
        "Queue writes are forbidden",
        "GO only for disabled executor execution plan preview",
    ):
        assert phrase in text


def test_package_sequence_records_1017_1024():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 1017-1024" in text
    assert "Runtime Executor Execution Plan Boundary (Disabled)" in text
