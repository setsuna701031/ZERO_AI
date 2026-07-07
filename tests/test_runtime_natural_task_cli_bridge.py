from __future__ import annotations

import inspect
import json

from core.runtime import runtime_natural_task_cli_bridge as bridge_module
from core.runtime.runtime_natural_task_cli_bridge import (
    RUNTIME_NATURAL_TASK_CLI_BRIDGE_SCHEMA,
    build_natural_task_cli_bridge,
    natural_task_cli_bridge_to_summary,
    validate_natural_task_cli_bridge,
)
from core.runtime.runtime_natural_task_package_generator import (
    RUNTIME_OPERATOR_PACKAGE_SCHEMA,
)
from cli import zero_natural_task_package_generator as cli_module


def test_bridge_builds_ready_package_and_command_plan() -> None:
    result = build_natural_task_cli_bridge(
        "Add a readiness review for natural task intake",
        target_root="E:/zero_ai",
        package_json_path="workspace/generated/natural_task_package.json",
    )

    assert result["schema"] == RUNTIME_NATURAL_TASK_CLI_BRIDGE_SCHEMA
    assert result["ok"] is True
    assert result["bridge_status"] == "ready"
    assert result["package_schema"] == RUNTIME_OPERATOR_PACKAGE_SCHEMA
    assert result["runtime_operator_package"]["goal"] == (
        "Add a readiness review for natural task intake"
    )
    assert result["runtime_operator_package"]["target_root"] == "E:/zero_ai"
    assert result["runtime_operator_package"]["requested_mode"] == "controlled"
    assert result["command_plan"]["argv"] == [
        "python",
        "-m",
        "cli.zero_operator_console",
        "run",
        "workspace/generated/natural_task_package.json",
        "--controlled",
    ]


def test_bridge_is_deterministic_for_same_input() -> None:
    first = build_natural_task_cli_bridge(
        "Create deterministic natural task bridge",
        target_root="E:/zero_ai",
        package_json_path="workspace/package.json",
    )
    second = build_natural_task_cli_bridge(
        "Create deterministic natural task bridge",
        target_root="E:/zero_ai",
        package_json_path="workspace/package.json",
    )

    assert first == second
    assert first["package_id"] == second["package_id"]
    assert first["command_plan"] == second["command_plan"]


def test_bridge_never_executes_or_writes_package_json() -> None:
    result = build_natural_task_cli_bridge("Prepare package only")

    assert result["package_json_written"] is False
    assert result["operator_console_started"] is False
    assert result["direct_dispatch_requested"] is False
    assert result["executor_invoked"] is False
    assert result["execution_started"] is False
    assert result["task_executed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["command_plan"]["command_executed"] is False
    assert result["command_plan"]["package_json_written"] is False


def test_bridge_denies_empty_task_without_execution() -> None:
    result = build_natural_task_cli_bridge("   ")

    assert result["ok"] is False
    assert result["bridge_status"] == "denied"
    assert result["denial_reason"] == "task_text_required"
    assert result["runtime_operator_package"] is None
    assert result["executor_invoked"] is False
    assert result["execution_started"] is False


def test_bridge_summary_is_stable_and_planning_only() -> None:
    result = build_natural_task_cli_bridge(
        "Summarize natural task bridge",
        package_json_path="workspace/generated.json",
    )
    summary = natural_task_cli_bridge_to_summary(result)

    assert summary == {
        "schema": RUNTIME_NATURAL_TASK_CLI_BRIDGE_SCHEMA,
        "ok": True,
        "bridge_status": "ready",
        "package_schema": RUNTIME_OPERATOR_PACKAGE_SCHEMA,
        "package_id": result["package_id"],
        "task_id": result["task_id"],
        "goal": "Summarize natural task bridge",
        "requested_mode": "controlled",
        "command_status": "planned",
        "package_json_path": "workspace/generated.json",
        "package_json_written": False,
        "operator_console_started": False,
        "executor_invoked": False,
        "execution_started": False,
        "task_executed": False,
    }


def test_validate_bridge_accepts_ready_bridge() -> None:
    result = build_natural_task_cli_bridge("Validate natural bridge")
    report = validate_natural_task_cli_bridge(result)

    assert report["schema"] == RUNTIME_NATURAL_TASK_CLI_BRIDGE_SCHEMA
    assert report["ok"] is True
    assert report["valid"] is True
    assert report["errors"] == []
    assert report["package_id"] == result["package_id"]


def test_validate_bridge_rejects_execution_claim() -> None:
    result = build_natural_task_cli_bridge("Reject execution claim")
    result["execution_started"] = True

    report = validate_natural_task_cli_bridge(result)

    assert report["ok"] is False
    assert "invalid:execution_started" in report["errors"]


def test_cli_prints_full_bridge_json(capsys) -> None:
    exit_code = cli_module.main(
        [
            "Create generated package from CLI",
            "--target-root",
            "E:/zero_ai",
            "--package-json-path",
            "workspace/generated/package.json",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["schema"] == RUNTIME_NATURAL_TASK_CLI_BRIDGE_SCHEMA
    assert payload["ok"] is True
    assert payload["runtime_operator_package"]["goal"] == (
        "Create generated package from CLI"
    )
    assert payload["command_plan"]["package_json_path"] == (
        "workspace/generated/package.json"
    )
    assert payload["operator_console_started"] is False


def test_cli_prints_summary_json(capsys) -> None:
    exit_code = cli_module.main(["Create summary", "--summary"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["schema"] == RUNTIME_NATURAL_TASK_CLI_BRIDGE_SCHEMA
    assert payload["bridge_status"] == "ready"
    assert "runtime_operator_package" not in payload
    assert payload["operator_console_started"] is False


def test_cli_module_does_not_import_operator_service_or_dispatch_calls() -> None:
    source = inspect.getsource(cli_module)
    forbidden_terms = (
        "RuntimeOperatorService",
        "run_package(",
        "run_goal(",
        "subprocess",
        "requests",
        "commit(",
        "git ",
    )

    for term in forbidden_terms:
        assert term not in source


def test_bridge_module_does_not_import_io_or_runtime_execution() -> None:
    source = inspect.getsource(bridge_module)
    forbidden_terms = (
        "subprocess",
        "open(",
        "Path(",
        "os.",
        "requests",
        "RuntimeOperatorService",
        "run_package(",
        "run_goal(",
        "commit(",
        "git ",
    )

    for term in forbidden_terms:
        assert term not in source
