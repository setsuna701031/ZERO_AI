import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_scheduler_planning.py"
DOC = ROOT / "docs/runtime_activation_scheduler_planning.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_scheduler_planning_imports_and_public_api_exists():
    from core.runtime import runtime_activation_scheduler_planning

    assert hasattr(
        runtime_activation_scheduler_planning,
        "preview_runtime_activation_scheduler_planning",
    )
    assert runtime_activation_scheduler_planning.__all__ == [
        "preview_runtime_activation_scheduler_planning"
    ]


def test_scheduler_planning_preview_is_deterministic():
    from core.runtime.runtime_activation_scheduler_planning import (
        preview_runtime_activation_scheduler_planning,
    )

    intake = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
        "scheduler_status": "disabled",
        "scheduler_reason": "scheduler_intake_disabled",
        "scheduler_available": False,
    }

    first = preview_runtime_activation_scheduler_planning(intake)
    second = preview_runtime_activation_scheduler_planning(intake)

    assert first == second
    assert first["mode"] == "scheduler_planning_preview"
    assert first["planning_status"] == "disabled"
    assert first["planning_reason"] == "scheduler_planning_disabled"
    assert first["result"] == "blocked"


def test_scheduler_planning_keeps_planning_scheduling_and_execution_disabled():
    from core.runtime.runtime_activation_scheduler_planning import (
        preview_runtime_activation_scheduler_planning,
    )

    result = preview_runtime_activation_scheduler_planning({})

    assert result["scheduler_planning_ready"] is True
    assert result["scheduling_plan_created"] is False
    assert result["scheduling_allowed"] is False
    assert result["dispatch_allowed"] is False
    assert result["execution_allowed"] is False
    assert result["runtime_mutation_allowed"] is False


def test_scheduler_planning_prepares_future_plan_metadata():
    from core.runtime.runtime_activation_scheduler_planning import (
        preview_runtime_activation_scheduler_planning,
    )

    result = preview_runtime_activation_scheduler_planning({})

    assert result["scheduling_plan_preview"] == {
        "plan_layer": "runtime_scheduler_planning",
        "plan_created": False,
        "scheduling_enabled": False,
        "dispatch_enabled": False,
        "execution_enabled": False,
    }


def test_scheduler_planning_preserves_intake_metadata():
    from core.runtime.runtime_activation_scheduler_planning import (
        preview_runtime_activation_scheduler_planning,
    )

    intake = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "scheduler_status": "disabled",
        "scheduler_reason": "scheduler_intake_disabled",
        "scheduler_intake_ready": True,
        "scheduler_available": False,
        "scheduler_task_received": False,
        "scheduling_allowed": False,
        "execution_allowed": False,
        "visibility_snapshot": {
            "visibility_status": "disabled",
            "queue_visible": False,
        },
        "future_scheduler_intake_preview": {
            "scheduler_available": False,
            "task_receive_enabled": False,
        },
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "scheduler_status": "disabled",
        "scheduler_reason": "scheduler_intake_disabled",
        "scheduler_intake_ready": True,
        "scheduler_available": False,
        "scheduler_task_received": False,
        "scheduling_allowed": False,
        "execution_allowed": False,
        "visibility_snapshot": {
            "visibility_status": "disabled",
            "queue_visible": False,
        },
        "future_scheduler_intake_preview": {
            "scheduler_available": False,
            "task_receive_enabled": False,
        },
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_scheduler_planning(intake)

    assert intake == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == [
        "execution_allowed",
        "extra",
        "future_scheduler_intake_preview",
        "identity_snapshot",
        "lineage_snapshot",
        "scheduler_available",
        "scheduler_intake_ready",
        "scheduler_reason",
        "scheduler_status",
        "scheduler_task_received",
        "scheduling_allowed",
        "visibility_snapshot",
    ]
    assert result["identity_snapshot"] == {
        "task_id": "task-1",
        "task_name": "Preview",
    }
    assert result["lineage_snapshot"] == {
        "lineage_id": "lineage-1",
        "trace_id": "trace-1",
    }
    assert result["scheduler_intake_snapshot"] == {
        "scheduler_status": "disabled",
        "scheduler_reason": "scheduler_intake_disabled",
        "scheduler_intake_ready": True,
        "scheduler_available": False,
        "scheduler_task_received": False,
        "scheduling_allowed": False,
        "execution_allowed": False,
        "visibility_snapshot": {
            "queue_visible": False,
            "visibility_status": "disabled",
        },
        "future_scheduler_intake_preview": {
            "scheduler_available": False,
            "task_receive_enabled": False,
        },
    }


def test_scheduler_planning_has_no_io_or_mutation_flags():
    from core.runtime.runtime_activation_scheduler_planning import (
        preview_runtime_activation_scheduler_planning,
    )

    result = preview_runtime_activation_scheduler_planning({})

    assert result["queue_read_allowed"] is False
    assert result["queue_write_allowed"] is False
    assert result["filesystem_io_allowed"] is False
    assert result["database_io_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_scheduler_planning_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_scheduler_planning import (
        preview_runtime_activation_scheduler_planning,
    )

    result = preview_runtime_activation_scheduler_planning({})

    assert result["scheduler_runtime_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False


def test_scheduler_planning_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_scheduler_planning import (
        preview_runtime_activation_scheduler_planning,
    )

    none_result = preview_runtime_activation_scheduler_planning(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["scheduling_plan_created"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_scheduler_planning(malformed)
        assert result["scheduling_plan_created"] is False
        assert result["scheduling_allowed"] is False
        assert result["dispatch_allowed"] is False
        assert result["execution_allowed"] is False
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


def test_docs_explain_disabled_scheduler_planning():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "must not schedule, dispatch, or execute tasks",
        "Scheduler runtime imports and calls are forbidden",
        "Executor imports and calls are forbidden",
        "Queue reads are forbidden",
        "Queue writes are forbidden",
        "Filesystem IO is forbidden",
        "Database IO is forbidden",
        "GO only for disabled scheduler planning preview",
    ):
        assert phrase in text


def test_package_sequence_records_977_984():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 977-984" in text
    assert "Runtime Scheduler Planning Boundary (Disabled)" in text
