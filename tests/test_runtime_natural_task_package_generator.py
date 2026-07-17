from __future__ import annotations

import inspect

from core.runtime import runtime_natural_task_package_generator as generator
from core.runtime.runtime_natural_task_package_generator import (
    RUNTIME_NATURAL_TASK_PACKAGE_GENERATOR_SCHEMA,
    RUNTIME_OPERATOR_PACKAGE_SCHEMA,
    build_runtime_operator_package_from_task,
    runtime_operator_package_to_summary,
    validate_generated_runtime_operator_package,
)


def _package(task_text: str = "Add a readiness report and focused test") -> dict:
    result = build_runtime_operator_package_from_task(
        task_text,
        target_root="E:/zero_ai",
    )
    assert result["ok"] is True
    return result["runtime_operator_package"]


def test_generator_returns_required_runtime_operator_package_shape() -> None:
    package = _package()

    assert package["schema"] == RUNTIME_OPERATOR_PACKAGE_SCHEMA
    assert package["package_id"].startswith("runtime-package-")
    assert package["task_id"].startswith("task-")
    assert package["goal"] == "Add a readiness report and focused test"
    assert package["requested_mode"] == "controlled"
    assert package["target_root"] == "E:/zero_ai"
    assert isinstance(package["requested_changes"], list)
    assert package["requested_changes"]
    assert package["validation_required"] is True
    assert package["rollback_required"] is True
    assert isinstance(package["authority_context"], dict)


def test_authority_context_blocks_bypass_and_requires_operator_service() -> None:
    package = _package("Update docs without bypassing ZERO")
    authority = package["authority_context"]

    assert authority["authority_source"] == "natural_task_package_generator"
    assert authority["operator_service_required"] is True
    assert authority["controlled_execution_required"] is True
    assert authority["validation_required"] is True
    assert authority["rollback_required"] is True
    assert authority["direct_dispatch_allowed"] is False
    assert authority["executor_bypass_allowed"] is False


def test_generation_result_never_executes_or_dispatches() -> None:
    result = build_runtime_operator_package_from_task("Prepare a controlled package")

    assert result["schema"] == RUNTIME_NATURAL_TASK_PACKAGE_GENERATOR_SCHEMA
    assert result["ok"] is True
    assert result["package_generation_status"] == "generated"
    assert result["direct_dispatch_requested"] is False
    assert result["executor_invoked"] is False
    assert result["execution_started"] is False
    assert result["task_executed"] is False
    assert result["runtime_state_mutated"] is False


def test_generation_is_deterministic_for_same_task() -> None:
    first = build_runtime_operator_package_from_task(
        "Create operator package generator tests",
        target_root="E:/zero_ai",
    )
    second = build_runtime_operator_package_from_task(
        "Create operator package generator tests",
        target_root="E:/zero_ai",
    )

    assert first == second
    assert first["package_id"] == second["package_id"]
    assert first["task_id"] == second["task_id"]


def test_generation_changes_identity_when_task_changes() -> None:
    first = build_runtime_operator_package_from_task("Task A", target_root="E:/zero_ai")
    second = build_runtime_operator_package_from_task("Task B", target_root="E:/zero_ai")

    assert first["package_id"] != second["package_id"]
    assert first["task_id"] != second["task_id"]


def test_empty_task_is_denied_without_package() -> None:
    result = build_runtime_operator_package_from_task("   ")

    assert result["ok"] is False
    assert result["package_generation_status"] == "denied"
    assert result["denial_reason"] == "task_text_required"
    assert result["runtime_operator_package"] is None
    assert result["executor_invoked"] is False
    assert result["execution_started"] is False


def test_validate_generated_package_accepts_generator_output() -> None:
    package = _package("Create validation package")
    report = validate_generated_runtime_operator_package(package)

    assert report["schema"] == RUNTIME_NATURAL_TASK_PACKAGE_GENERATOR_SCHEMA
    assert report["ok"] is True
    assert report["valid"] is True
    assert report["errors"] == []
    assert report["package_id"] == package["package_id"]
    assert report["task_id"] == package["task_id"]


def test_validate_generated_package_rejects_executor_bypass() -> None:
    package = _package("Reject bypass")
    package["authority_context"]["executor_bypass_allowed"] = True

    report = validate_generated_runtime_operator_package(package)

    assert report["ok"] is False
    assert report["valid"] is False
    assert "invalid:executor_bypass_allowed" in report["errors"]


def test_summary_is_stable_and_does_not_claim_execution() -> None:
    result = build_runtime_operator_package_from_task("Summarize generated package")
    summary = runtime_operator_package_to_summary(result)

    assert summary == {
        "schema": RUNTIME_NATURAL_TASK_PACKAGE_GENERATOR_SCHEMA,
        "ok": True,
        "package_generation_status": "generated",
        "package_id": result["package_id"],
        "task_id": result["task_id"],
        "goal": "Summarize generated package",
        "requested_mode": "controlled",
        "validation_required": True,
        "rollback_required": True,
        "direct_dispatch_requested": False,
        "executor_invoked": False,
        "execution_started": False,
        "task_executed": False,
    }


def test_custom_requested_changes_are_preserved_by_value() -> None:
    changes = [
        {
            "change_id": "change-1",
            "change_type": "doc_update",
            "target_path": "docs/example.md",
            "operation": "replace_file",
        }
    ]
    result = build_runtime_operator_package_from_task(
        "Update docs/example.md",
        requested_changes=changes,
    )
    package = result["runtime_operator_package"]

    assert package["requested_changes"] == changes
    changes[0]["operation"] = "mutated_after_call"
    assert package["requested_changes"][0]["operation"] == "replace_file"


def test_module_has_no_runtime_execution_or_io_imports() -> None:
    source = inspect.getsource(generator)
    forbidden_terms = (
        "subprocess",
        "open(",
        "Path(",
        "os.",
        "requests",
        "RuntimeOperatorService",
        "zero_operator_console",
        "run_package(",
        "run_goal(",
        "commit(",
        "git ",
    )

    for term in forbidden_terms:
        assert term not in source
