import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_scheduler_dispatch.py"
DOC = ROOT / "docs/runtime_activation_scheduler_dispatch.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_scheduler_dispatch_imports_and_public_api_exists():
    from core.runtime import runtime_activation_scheduler_dispatch

    assert hasattr(
        runtime_activation_scheduler_dispatch,
        "preview_runtime_activation_scheduler_dispatch",
    )
    assert runtime_activation_scheduler_dispatch.__all__ == [
        "preview_runtime_activation_scheduler_dispatch"
    ]


def test_scheduler_dispatch_preview_is_deterministic():
    from core.runtime.runtime_activation_scheduler_dispatch import (
        preview_runtime_activation_scheduler_dispatch,
    )

    planning = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
        "planning_status": "disabled",
        "planning_reason": "scheduler_planning_disabled",
        "scheduling_plan_created": False,
    }

    first = preview_runtime_activation_scheduler_dispatch(planning)
    second = preview_runtime_activation_scheduler_dispatch(planning)

    assert first == second
    assert first["mode"] == "scheduler_dispatch_preview"
    assert first["dispatch_status"] == "disabled"
    assert first["dispatch_reason"] == "scheduler_dispatch_disabled"
    assert first["result"] == "blocked"


def test_scheduler_dispatch_keeps_dispatch_and_execution_disabled():
    from core.runtime.runtime_activation_scheduler_dispatch import (
        preview_runtime_activation_scheduler_dispatch,
    )

    result = preview_runtime_activation_scheduler_dispatch({})

    assert result["scheduler_dispatch_ready"] is True
    assert result["dispatch_created"] is False
    assert result["dispatch_allowed"] is False
    assert result["execution_allowed"] is False
    assert result["executor_admission_allowed"] is False
    assert result["runtime_mutation_allowed"] is False


def test_scheduler_dispatch_prepares_future_dispatch_metadata():
    from core.runtime.runtime_activation_scheduler_dispatch import (
        preview_runtime_activation_scheduler_dispatch,
    )

    result = preview_runtime_activation_scheduler_dispatch({})

    assert result["dispatch_preview"] == {
        "dispatch_layer": "runtime_scheduler_dispatch",
        "dispatch_created": False,
        "dispatch_enabled": False,
        "executor_admission_enabled": False,
        "execution_enabled": False,
    }


def test_scheduler_dispatch_preserves_planning_metadata():
    from core.runtime.runtime_activation_scheduler_dispatch import (
        preview_runtime_activation_scheduler_dispatch,
    )

    planning = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "planning_status": "disabled",
        "planning_reason": "scheduler_planning_disabled",
        "scheduler_planning_ready": True,
        "scheduling_plan_created": False,
        "scheduling_allowed": False,
        "dispatch_allowed": False,
        "execution_allowed": False,
        "scheduler_intake_snapshot": {
            "scheduler_status": "disabled",
            "scheduler_task_received": False,
        },
        "scheduling_plan_preview": {
            "plan_created": False,
            "dispatch_enabled": False,
        },
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "planning_status": "disabled",
        "planning_reason": "scheduler_planning_disabled",
        "scheduler_planning_ready": True,
        "scheduling_plan_created": False,
        "scheduling_allowed": False,
        "dispatch_allowed": False,
        "execution_allowed": False,
        "scheduler_intake_snapshot": {
            "scheduler_status": "disabled",
            "scheduler_task_received": False,
        },
        "scheduling_plan_preview": {
            "plan_created": False,
            "dispatch_enabled": False,
        },
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_scheduler_dispatch(planning)

    assert planning == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == [
        "dispatch_allowed",
        "execution_allowed",
        "extra",
        "identity_snapshot",
        "lineage_snapshot",
        "planning_reason",
        "planning_status",
        "scheduler_intake_snapshot",
        "scheduler_planning_ready",
        "scheduling_allowed",
        "scheduling_plan_created",
        "scheduling_plan_preview",
    ]
    assert result["identity_snapshot"] == {
        "task_id": "task-1",
        "task_name": "Preview",
    }
    assert result["lineage_snapshot"] == {
        "lineage_id": "lineage-1",
        "trace_id": "trace-1",
    }
    assert result["scheduler_planning_snapshot"] == {
        "planning_status": "disabled",
        "planning_reason": "scheduler_planning_disabled",
        "scheduler_planning_ready": True,
        "scheduling_plan_created": False,
        "scheduling_allowed": False,
        "dispatch_allowed": False,
        "execution_allowed": False,
        "scheduler_intake_snapshot": {
            "scheduler_status": "disabled",
            "scheduler_task_received": False,
        },
        "scheduling_plan_preview": {
            "dispatch_enabled": False,
            "plan_created": False,
        },
    }


def test_scheduler_dispatch_has_no_io_or_mutation_flags():
    from core.runtime.runtime_activation_scheduler_dispatch import (
        preview_runtime_activation_scheduler_dispatch,
    )

    result = preview_runtime_activation_scheduler_dispatch({})

    assert result["queue_read_allowed"] is False
    assert result["queue_write_allowed"] is False
    assert result["filesystem_io_allowed"] is False
    assert result["database_io_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_scheduler_dispatch_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_scheduler_dispatch import (
        preview_runtime_activation_scheduler_dispatch,
    )

    result = preview_runtime_activation_scheduler_dispatch({})

    assert result["scheduler_runtime_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False


def test_scheduler_dispatch_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_scheduler_dispatch import (
        preview_runtime_activation_scheduler_dispatch,
    )

    none_result = preview_runtime_activation_scheduler_dispatch(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["dispatch_created"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_scheduler_dispatch(malformed)
        assert result["dispatch_created"] is False
        assert result["dispatch_allowed"] is False
        assert result["execution_allowed"] is False
        assert result["executor_admission_allowed"] is False
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


def test_docs_explain_disabled_scheduler_dispatch():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "must not dispatch or execute tasks",
        "Scheduler runtime calls are forbidden",
        "Executor imports and calls are forbidden",
        "Queue reads are forbidden",
        "Queue writes are forbidden",
        "Filesystem IO is forbidden",
        "Database IO is forbidden",
        "GO only for disabled scheduler dispatch preview",
    ):
        assert phrase in text


def test_package_sequence_records_985_992():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 985-992" in text
    assert "Runtime Scheduler Dispatch Boundary (Disabled)" in text
