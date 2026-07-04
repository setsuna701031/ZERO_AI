import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_queue_visibility_gate.py"
DOC = ROOT / "docs/runtime_activation_queue_visibility_gate.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_queue_visibility_gate_imports_and_public_api_exists():
    from core.runtime import runtime_activation_queue_visibility_gate

    assert hasattr(
        runtime_activation_queue_visibility_gate,
        "preview_runtime_activation_queue_visibility_gate",
    )
    assert runtime_activation_queue_visibility_gate.__all__ == [
        "preview_runtime_activation_queue_visibility_gate"
    ]


def test_queue_visibility_gate_preview_is_deterministic():
    from core.runtime.runtime_activation_queue_visibility_gate import (
        preview_runtime_activation_queue_visibility_gate,
    )

    transition = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
        "transition_status": "disabled",
        "transition_reason": "queue_state_transition_disabled",
    }

    first = preview_runtime_activation_queue_visibility_gate(transition)
    second = preview_runtime_activation_queue_visibility_gate(transition)

    assert first == second
    assert first["mode"] == "queue_visibility_gate_preview"
    assert first["visibility_status"] == "disabled"
    assert first["visibility_reason"] == "queue_visibility_gate_disabled"
    assert first["result"] == "blocked"


def test_queue_visibility_gate_keeps_queue_invisible():
    from core.runtime.runtime_activation_queue_visibility_gate import (
        preview_runtime_activation_queue_visibility_gate,
    )

    result = preview_runtime_activation_queue_visibility_gate({})

    assert result["visibility_gate_ready"] is True
    assert result["queue_visible"] is False
    assert result["scheduler_visibility_allowed"] is False
    assert result["task_discovery_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["queue_read_allowed"] is False
    assert result["queue_write_allowed"] is False


def test_queue_visibility_gate_prevents_scheduler_discovery():
    from core.runtime.runtime_activation_queue_visibility_gate import (
        preview_runtime_activation_queue_visibility_gate,
    )

    result = preview_runtime_activation_queue_visibility_gate({})

    assert result["future_scheduler_visibility_preview"] == {
        "visibility_layer": "runtime_queue_scheduler_discovery",
        "queue_visible": False,
        "scheduler_visibility_enabled": False,
        "task_discovery_enabled": False,
        "queue_read_enabled": False,
    }


def test_queue_visibility_gate_preserves_queue_state_metadata():
    from core.runtime.runtime_activation_queue_visibility_gate import (
        preview_runtime_activation_queue_visibility_gate,
    )

    transition = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "transition_status": "disabled",
        "transition_reason": "queue_state_transition_disabled",
        "transition_boundary_ready": True,
        "state_transition_prepared": True,
        "queue_state_update_allowed": False,
        "state_persistence_allowed": False,
        "mutation_result_snapshot": {
            "result_status": "disabled",
            "mutation_result_created": False,
        },
        "future_state_preview": {
            "transition_prepared": True,
            "queue_state_update_enabled": False,
        },
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "transition_status": "disabled",
        "transition_reason": "queue_state_transition_disabled",
        "transition_boundary_ready": True,
        "state_transition_prepared": True,
        "queue_state_update_allowed": False,
        "state_persistence_allowed": False,
        "mutation_result_snapshot": {
            "result_status": "disabled",
            "mutation_result_created": False,
        },
        "future_state_preview": {
            "transition_prepared": True,
            "queue_state_update_enabled": False,
        },
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_queue_visibility_gate(transition)

    assert transition == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == [
        "extra",
        "future_state_preview",
        "identity_snapshot",
        "lineage_snapshot",
        "mutation_result_snapshot",
        "queue_state_update_allowed",
        "state_persistence_allowed",
        "state_transition_prepared",
        "transition_boundary_ready",
        "transition_reason",
        "transition_status",
    ]
    assert result["identity_snapshot"] == {
        "task_id": "task-1",
        "task_name": "Preview",
    }
    assert result["lineage_snapshot"] == {
        "lineage_id": "lineage-1",
        "trace_id": "trace-1",
    }
    assert result["queue_state_snapshot"] == {
        "transition_status": "disabled",
        "transition_reason": "queue_state_transition_disabled",
        "transition_boundary_ready": True,
        "state_transition_prepared": True,
        "queue_state_update_allowed": False,
        "state_persistence_allowed": False,
        "mutation_result_snapshot": {
            "mutation_result_created": False,
            "result_status": "disabled",
        },
        "future_state_preview": {
            "queue_state_update_enabled": False,
            "transition_prepared": True,
        },
    }


def test_queue_visibility_gate_has_no_io_or_mutation_flags():
    from core.runtime.runtime_activation_queue_visibility_gate import (
        preview_runtime_activation_queue_visibility_gate,
    )

    result = preview_runtime_activation_queue_visibility_gate({})

    assert result["filesystem_io_allowed"] is False
    assert result["database_io_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_queue_visibility_gate_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_queue_visibility_gate import (
        preview_runtime_activation_queue_visibility_gate,
    )

    result = preview_runtime_activation_queue_visibility_gate({})

    assert result["scheduler_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False


def test_queue_visibility_gate_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_queue_visibility_gate import (
        preview_runtime_activation_queue_visibility_gate,
    )

    none_result = preview_runtime_activation_queue_visibility_gate(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["queue_visible"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_queue_visibility_gate(malformed)
        assert result["queue_visible"] is False
        assert result["scheduler_visibility_allowed"] is False
        assert result["task_discovery_allowed"] is False
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


def test_docs_explain_disabled_visibility_gate():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "must not expose tasks to scheduler",
        "Scheduler imports and calls are forbidden",
        "Executor imports and calls are forbidden",
        "Queue reads are forbidden",
        "Queue writes are forbidden",
        "Filesystem IO is forbidden",
        "Database IO is forbidden",
        "Tool execution is forbidden",
        "GO only for disabled queue visibility gate preview",
    ):
        assert phrase in text


def test_package_sequence_records_961_968():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 961-968" in text
    assert "Runtime Queue Visibility Gate (Disabled)" in text
