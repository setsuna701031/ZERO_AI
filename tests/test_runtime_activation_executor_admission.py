import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_executor_admission.py"
DOC = ROOT / "docs/runtime_activation_executor_admission.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_executor_admission_imports_and_public_api_exists():
    from core.runtime import runtime_activation_executor_admission

    assert hasattr(
        runtime_activation_executor_admission,
        "preview_runtime_activation_executor_admission",
    )
    assert runtime_activation_executor_admission.__all__ == [
        "preview_runtime_activation_executor_admission"
    ]


def test_executor_admission_preview_is_deterministic():
    from core.runtime.runtime_activation_executor_admission import (
        preview_runtime_activation_executor_admission,
    )

    dispatch = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
        "dispatch_status": "disabled",
        "dispatch_reason": "scheduler_dispatch_disabled",
        "dispatch_created": False,
    }

    first = preview_runtime_activation_executor_admission(dispatch)
    second = preview_runtime_activation_executor_admission(dispatch)

    assert first == second
    assert first["mode"] == "executor_admission_preview"
    assert first["admission_status"] == "disabled"
    assert first["admission_reason"] == "executor_admission_disabled"
    assert first["result"] == "blocked"


def test_executor_admission_remains_denied():
    from core.runtime.runtime_activation_executor_admission import (
        preview_runtime_activation_executor_admission,
    )

    result = preview_runtime_activation_executor_admission({})

    assert result["executor_admission_ready"] is True
    assert result["executor_available"] is False
    assert result["executor_admission_granted"] is False
    assert result["execution_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["runtime_mutation_allowed"] is False


def test_executor_admission_prepares_future_admission_metadata():
    from core.runtime.runtime_activation_executor_admission import (
        preview_runtime_activation_executor_admission,
    )

    result = preview_runtime_activation_executor_admission({})

    assert result["executor_admission_preview"] == {
        "admission_layer": "runtime_executor_admission",
        "executor_available": False,
        "admission_granted": False,
        "execution_enabled": False,
        "tool_execution_enabled": False,
    }


def test_executor_admission_preserves_scheduler_dispatch_metadata():
    from core.runtime.runtime_activation_executor_admission import (
        preview_runtime_activation_executor_admission,
    )

    dispatch = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "dispatch_status": "disabled",
        "dispatch_reason": "scheduler_dispatch_disabled",
        "scheduler_dispatch_ready": True,
        "dispatch_created": False,
        "dispatch_allowed": False,
        "execution_allowed": False,
        "executor_admission_allowed": False,
        "scheduler_planning_snapshot": {
            "planning_status": "disabled",
            "scheduling_plan_created": False,
        },
        "dispatch_preview": {
            "dispatch_created": False,
            "executor_admission_enabled": False,
        },
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "dispatch_status": "disabled",
        "dispatch_reason": "scheduler_dispatch_disabled",
        "scheduler_dispatch_ready": True,
        "dispatch_created": False,
        "dispatch_allowed": False,
        "execution_allowed": False,
        "executor_admission_allowed": False,
        "scheduler_planning_snapshot": {
            "planning_status": "disabled",
            "scheduling_plan_created": False,
        },
        "dispatch_preview": {
            "dispatch_created": False,
            "executor_admission_enabled": False,
        },
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_executor_admission(dispatch)

    assert dispatch == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == [
        "dispatch_allowed",
        "dispatch_created",
        "dispatch_preview",
        "dispatch_reason",
        "dispatch_status",
        "execution_allowed",
        "executor_admission_allowed",
        "extra",
        "identity_snapshot",
        "lineage_snapshot",
        "scheduler_dispatch_ready",
        "scheduler_planning_snapshot",
    ]
    assert result["identity_snapshot"] == {
        "task_id": "task-1",
        "task_name": "Preview",
    }
    assert result["lineage_snapshot"] == {
        "lineage_id": "lineage-1",
        "trace_id": "trace-1",
    }
    assert result["scheduler_dispatch_snapshot"] == {
        "dispatch_status": "disabled",
        "dispatch_reason": "scheduler_dispatch_disabled",
        "scheduler_dispatch_ready": True,
        "dispatch_created": False,
        "dispatch_allowed": False,
        "execution_allowed": False,
        "executor_admission_allowed": False,
        "scheduler_planning_snapshot": {
            "planning_status": "disabled",
            "scheduling_plan_created": False,
        },
        "dispatch_preview": {
            "dispatch_created": False,
            "executor_admission_enabled": False,
        },
    }


def test_executor_admission_has_no_io_or_mutation_flags():
    from core.runtime.runtime_activation_executor_admission import (
        preview_runtime_activation_executor_admission,
    )

    result = preview_runtime_activation_executor_admission({})

    assert result["queue_read_allowed"] is False
    assert result["queue_write_allowed"] is False
    assert result["filesystem_io_allowed"] is False
    assert result["database_io_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_executor_admission_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_executor_admission import (
        preview_runtime_activation_executor_admission,
    )

    result = preview_runtime_activation_executor_admission({})

    assert result["scheduler_runtime_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False


def test_executor_admission_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_executor_admission import (
        preview_runtime_activation_executor_admission,
    )

    none_result = preview_runtime_activation_executor_admission(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["executor_available"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_executor_admission(malformed)
        assert result["executor_available"] is False
        assert result["executor_admission_granted"] is False
        assert result["execution_allowed"] is False
        assert result["tool_execution_allowed"] is False
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


def test_docs_explain_disabled_executor_admission():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "must not admit, run, or execute tasks",
        "Executor imports and calls are forbidden",
        "Tool calls are forbidden",
        "Subprocess use is forbidden",
        "Scheduler runtime calls are forbidden",
        "Queue reads are forbidden",
        "Queue writes are forbidden",
        "GO only for disabled executor admission preview",
    ):
        assert phrase in text


def test_package_sequence_records_993_1000():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 993-1000" in text
    assert "Runtime Executor Admission Boundary (Disabled)" in text
