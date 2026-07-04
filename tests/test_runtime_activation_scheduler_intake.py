import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_scheduler_intake.py"
DOC = ROOT / "docs/runtime_activation_scheduler_intake.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_scheduler_intake_imports_and_public_api_exists():
    from core.runtime import runtime_activation_scheduler_intake

    assert hasattr(
        runtime_activation_scheduler_intake,
        "preview_runtime_activation_scheduler_intake",
    )
    assert runtime_activation_scheduler_intake.__all__ == [
        "preview_runtime_activation_scheduler_intake"
    ]


def test_scheduler_intake_preview_is_deterministic():
    from core.runtime.runtime_activation_scheduler_intake import (
        preview_runtime_activation_scheduler_intake,
    )

    visibility = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
        "visibility_status": "disabled",
        "visibility_reason": "queue_visibility_gate_disabled",
        "queue_visible": False,
    }

    first = preview_runtime_activation_scheduler_intake(visibility)
    second = preview_runtime_activation_scheduler_intake(visibility)

    assert first == second
    assert first["mode"] == "scheduler_intake_preview"
    assert first["scheduler_status"] == "disabled"
    assert first["scheduler_reason"] == "scheduler_intake_disabled"
    assert first["result"] == "blocked"


def test_scheduler_intake_keeps_scheduler_unavailable():
    from core.runtime.runtime_activation_scheduler_intake import (
        preview_runtime_activation_scheduler_intake,
    )

    result = preview_runtime_activation_scheduler_intake({})

    assert result["scheduler_intake_ready"] is True
    assert result["scheduler_available"] is False
    assert result["scheduler_task_received"] is False
    assert result["scheduling_allowed"] is False
    assert result["execution_allowed"] is False
    assert result["runtime_mutation_allowed"] is False


def test_scheduler_intake_cannot_receive_or_discover_task():
    from core.runtime.runtime_activation_scheduler_intake import (
        preview_runtime_activation_scheduler_intake,
    )

    result = preview_runtime_activation_scheduler_intake({})

    assert result["future_scheduler_intake_preview"] == {
        "intake_layer": "runtime_scheduler_visible_queue_task",
        "scheduler_available": False,
        "task_receive_enabled": False,
        "scheduling_enabled": False,
        "execution_enabled": False,
    }
    assert result["scheduler_task_received"] is False
    assert result["queue_read_allowed"] is False


def test_scheduler_intake_preserves_visibility_metadata():
    from core.runtime.runtime_activation_scheduler_intake import (
        preview_runtime_activation_scheduler_intake,
    )

    visibility = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "visibility_status": "disabled",
        "visibility_reason": "queue_visibility_gate_disabled",
        "visibility_gate_ready": True,
        "queue_visible": False,
        "scheduler_visibility_allowed": False,
        "task_discovery_allowed": False,
        "queue_state_snapshot": {
            "transition_status": "disabled",
            "queue_state_update_allowed": False,
        },
        "future_scheduler_visibility_preview": {
            "queue_visible": False,
            "task_discovery_enabled": False,
        },
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "visibility_status": "disabled",
        "visibility_reason": "queue_visibility_gate_disabled",
        "visibility_gate_ready": True,
        "queue_visible": False,
        "scheduler_visibility_allowed": False,
        "task_discovery_allowed": False,
        "queue_state_snapshot": {
            "transition_status": "disabled",
            "queue_state_update_allowed": False,
        },
        "future_scheduler_visibility_preview": {
            "queue_visible": False,
            "task_discovery_enabled": False,
        },
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_scheduler_intake(visibility)

    assert visibility == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == [
        "extra",
        "future_scheduler_visibility_preview",
        "identity_snapshot",
        "lineage_snapshot",
        "queue_state_snapshot",
        "queue_visible",
        "scheduler_visibility_allowed",
        "task_discovery_allowed",
        "visibility_gate_ready",
        "visibility_reason",
        "visibility_status",
    ]
    assert result["identity_snapshot"] == {
        "task_id": "task-1",
        "task_name": "Preview",
    }
    assert result["lineage_snapshot"] == {
        "lineage_id": "lineage-1",
        "trace_id": "trace-1",
    }
    assert result["visibility_snapshot"] == {
        "visibility_status": "disabled",
        "visibility_reason": "queue_visibility_gate_disabled",
        "visibility_gate_ready": True,
        "queue_visible": False,
        "scheduler_visibility_allowed": False,
        "task_discovery_allowed": False,
        "queue_state_snapshot": {
            "queue_state_update_allowed": False,
            "transition_status": "disabled",
        },
        "future_scheduler_visibility_preview": {
            "queue_visible": False,
            "task_discovery_enabled": False,
        },
    }


def test_scheduler_intake_has_no_io_or_mutation_flags():
    from core.runtime.runtime_activation_scheduler_intake import (
        preview_runtime_activation_scheduler_intake,
    )

    result = preview_runtime_activation_scheduler_intake({})

    assert result["queue_read_allowed"] is False
    assert result["queue_write_allowed"] is False
    assert result["filesystem_io_allowed"] is False
    assert result["database_io_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_scheduler_intake_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_scheduler_intake import (
        preview_runtime_activation_scheduler_intake,
    )

    result = preview_runtime_activation_scheduler_intake({})

    assert result["scheduler_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False


def test_scheduler_intake_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_scheduler_intake import (
        preview_runtime_activation_scheduler_intake,
    )

    none_result = preview_runtime_activation_scheduler_intake(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["scheduler_available"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_scheduler_intake(malformed)
        assert result["scheduler_available"] is False
        assert result["scheduler_task_received"] is False
        assert result["scheduling_allowed"] is False
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


def test_docs_explain_disabled_scheduler_intake():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "must not schedule or execute tasks",
        "Scheduler imports are forbidden",
        "Scheduler calls are forbidden",
        "Executor imports and calls are forbidden",
        "Queue reads are forbidden",
        "Queue writes are forbidden",
        "Filesystem IO is forbidden",
        "Database IO is forbidden",
        "GO only for disabled scheduler intake preview",
    ):
        assert phrase in text


def test_package_sequence_records_969_976():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 969-976" in text
    assert "Runtime Scheduler Intake Boundary (Disabled)" in text
