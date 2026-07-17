import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "core/runtime/runtime_activation_executor_execution_start.py"
DOC = ROOT / "docs/runtime_activation_executor_execution_start.md"
PACKAGE_SEQUENCE = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def test_executor_execution_start_imports_and_public_api_exists():
    from core.runtime import runtime_activation_executor_execution_start

    assert hasattr(
        runtime_activation_executor_execution_start,
        "preview_runtime_activation_executor_execution_start",
    )
    assert runtime_activation_executor_execution_start.__all__ == [
        "preview_runtime_activation_executor_execution_start"
    ]


def test_executor_execution_start_preview_is_deterministic():
    from core.runtime.runtime_activation_executor_execution_start import (
        preview_runtime_activation_executor_execution_start,
    )

    authorization = {
        "identity_snapshot": {"task_id": "task-1", "task_name": "Preview"},
        "lineage_snapshot": {"lineage_id": "lineage-1", "trace_id": "trace-1"},
        "authorization_status": "disabled",
        "authorization_reason": "executor_execution_authorization_disabled",
        "execution_authorized": False,
    }

    first = preview_runtime_activation_executor_execution_start(authorization)
    second = preview_runtime_activation_executor_execution_start(authorization)

    assert first == second
    assert first["mode"] == "executor_execution_start_preview"
    assert first["execution_start_status"] == "disabled"
    assert first["execution_start_reason"] == "executor_execution_start_disabled"
    assert first["result"] == "blocked"


def test_executor_execution_start_remains_disabled():
    from core.runtime.runtime_activation_executor_execution_start import (
        preview_runtime_activation_executor_execution_start,
    )

    result = preview_runtime_activation_executor_execution_start({})

    assert result["execution_start_boundary_ready"] is True
    assert result["executor_runtime_available"] is False
    assert result["execution_start_requested"] is False
    assert result["execution_start_allowed"] is False
    assert result["execution_started"] is False
    assert result["execution_completed"] is False
    assert result["execution_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["tool_call_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["repo_mutation_allowed"] is False


def test_executor_execution_start_prepares_future_start_metadata():
    from core.runtime.runtime_activation_executor_execution_start import (
        preview_runtime_activation_executor_execution_start,
    )

    result = preview_runtime_activation_executor_execution_start({})

    assert result["execution_start_preview"] == {
        "start_layer": "runtime_executor_execution_start",
        "executor_runtime_available": False,
        "execution_start_enabled": False,
        "execution_started": False,
        "execution_completed": False,
        "tool_execution_enabled": False,
        "repo_mutation_enabled": False,
    }


def test_executor_execution_start_preserves_authorization_metadata():
    from core.runtime.runtime_activation_executor_execution_start import (
        preview_runtime_activation_executor_execution_start,
    )

    authorization = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "authorization_status": "disabled",
        "authorization_reason": "executor_execution_authorization_disabled",
        "execution_authorization_ready": True,
        "execution_authorized": False,
        "executor_start_allowed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "execution_plan_snapshot": {
            "execution_plan_status": "disabled",
            "execution_plan_created": False,
        },
        "execution_authorization_preview": {
            "authorization_layer": "runtime_executor_execution_authorization",
            "execution_authorized": False,
        },
        "extra": {"nested": True},
    }
    original = {
        "identity_snapshot": {"task_name": "Preview", "task_id": "task-1"},
        "lineage_snapshot": {"trace_id": "trace-1", "lineage_id": "lineage-1"},
        "authorization_status": "disabled",
        "authorization_reason": "executor_execution_authorization_disabled",
        "execution_authorization_ready": True,
        "execution_authorized": False,
        "executor_start_allowed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "execution_plan_snapshot": {
            "execution_plan_status": "disabled",
            "execution_plan_created": False,
        },
        "execution_authorization_preview": {
            "authorization_layer": "runtime_executor_execution_authorization",
            "execution_authorized": False,
        },
        "extra": {"nested": True},
    }

    result = preview_runtime_activation_executor_execution_start(authorization)

    assert authorization == original
    assert result["input_present"] is True
    assert result["input_type"] == "dict"
    assert result["input_keys"] == [
        "authorization_reason",
        "authorization_status",
        "execution_allowed",
        "execution_authorization_preview",
        "execution_authorization_ready",
        "execution_authorized",
        "execution_plan_snapshot",
        "executor_start_allowed",
        "extra",
        "identity_snapshot",
        "lineage_snapshot",
        "repo_mutation_allowed",
        "runtime_mutation_allowed",
        "tool_call_allowed",
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
    assert result["execution_authorization_snapshot"] == {
        "authorization_status": "disabled",
        "authorization_reason": "executor_execution_authorization_disabled",
        "execution_authorization_ready": True,
        "execution_authorized": False,
        "executor_start_allowed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "execution_plan_snapshot": {
            "execution_plan_created": False,
            "execution_plan_status": "disabled",
        },
        "execution_authorization_preview": {
            "authorization_layer": "runtime_executor_execution_authorization",
            "execution_authorized": False,
        },
    }


def test_executor_execution_start_has_no_io_or_mutation_flags():
    from core.runtime.runtime_activation_executor_execution_start import (
        preview_runtime_activation_executor_execution_start,
    )

    result = preview_runtime_activation_executor_execution_start({})

    assert result["queue_read_allowed"] is False
    assert result["queue_write_allowed"] is False
    assert result["filesystem_io_allowed"] is False
    assert result["database_io_allowed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["repo_state_mutated"] is False


def test_executor_execution_start_has_no_downstream_dependency_flags():
    from core.runtime.runtime_activation_executor_execution_start import (
        preview_runtime_activation_executor_execution_start,
    )

    result = preview_runtime_activation_executor_execution_start({})

    assert result["scheduler_runtime_call_allowed"] is False
    assert result["executor_call_allowed"] is False
    assert result["tool_import_allowed"] is False
    assert result["tool_call_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["subprocess_allowed"] is False
    assert result["background_worker_started"] is False


def test_executor_execution_start_handles_none_and_malformed_input():
    from core.runtime.runtime_activation_executor_execution_start import (
        preview_runtime_activation_executor_execution_start,
    )

    none_result = preview_runtime_activation_executor_execution_start(None)
    assert none_result["input_present"] is False
    assert none_result["input_type"] == "NoneType"
    assert none_result["input_keys"] == []
    assert none_result["execution_start_allowed"] is False

    for malformed in ("bad", 7, ["not", "mapping"], object()):
        result = preview_runtime_activation_executor_execution_start(malformed)
        assert result["executor_runtime_available"] is False
        assert result["execution_start_requested"] is False
        assert result["execution_start_allowed"] is False
        assert result["execution_started"] is False
        assert result["execution_completed"] is False
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


def test_docs_explain_disabled_executor_execution_start():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for phrase in (
        "preview-only",
        "disabled executor execution start boundary",
        "Tool imports and calls are forbidden",
        "Executor imports and calls are forbidden",
        "Subprocess use is forbidden",
        "Scheduler runtime calls are forbidden",
        "Queue reads are forbidden",
        "Queue writes are forbidden",
        "GO only for disabled executor execution start preview",
    ):
        assert phrase in text


def test_package_sequence_records_1033_1040():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "Packages 1033-1040" in text
    assert "Runtime Executor Execution Start Boundary (Disabled)" in text
