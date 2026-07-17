from __future__ import annotations

import json
from pathlib import Path

from cli.zero_runtime_cli import main as zero_runtime_main
from core.runtime.runtime_goal_intake import (
    adapt_goal_to_runtime_work_package,
    build_goal_intake_record,
)
from core.runtime.runtime_goal_session_launcher import (
    build_runtime_session_launch_request,
    evaluate_session_launch_admission,
    launch_goal_session,
)
from core.runtime.runtime_operator_config import RuntimeOperatorConfig
from core.runtime.runtime_operator_service import RuntimeOperatorService


def _config(tmp_path: Path, **overrides):
    data = {
        "runtime_mode": "autonomous",
        "max_tick_limit": 3,
        "checkpoint_path": str(tmp_path / "goal-launch-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def test_1761_goal_text_creates_deterministic_intake_record() -> None:
    first = build_goal_intake_record("fix failing tests")
    second = build_goal_intake_record("fix failing tests")

    assert first == second
    assert first["goal_valid"] is True
    assert first["goal_id"].startswith("runtime-goal::")
    assert first["goal_text"] == "fix failing tests"
    assert first["runtime_state_mutated"] is False
    assert first["task_executed"] is False


def test_1764_empty_goal_denies() -> None:
    goal = build_goal_intake_record("   ")
    package = adapt_goal_to_runtime_work_package(goal)
    launch = launch_goal_session("   ", RuntimeOperatorConfig(runtime_mode="autonomous"))

    assert goal["goal_valid"] is False
    assert goal["denial_reason"] == "empty_goal_text"
    assert package["work_package_created"] is False
    assert launch["launch_admitted"] is False
    assert launch["denial_reason"] == "empty_goal_text"


def test_1767_goal_adapts_to_runtime_work_package_data() -> None:
    goal = build_goal_intake_record("demo goal")
    package = adapt_goal_to_runtime_work_package(goal)

    assert package["work_package_created"] is True
    assert package["work_package_id"].startswith("runtime-work-package::")
    assert package["goal_id"] == goal["goal_id"]
    assert package["goal_text"] == "demo goal"
    assert package["work_package_status"] == "launch_ready"
    assert package["task_executed"] is False
    assert package["direct_dispatch_requested"] is False


def test_1770_valid_goal_launches_session_record(tmp_path: Path) -> None:
    result = launch_goal_session("fix failing tests", _config(tmp_path))

    assert result["ok"] is True
    assert result["launch_admitted"] is True
    assert result["goal_id"].startswith("runtime-goal::")
    assert result["work_package_id"].startswith("runtime-work-package::")
    assert result["runtime_session_id"].startswith("runtime-session::")
    assert result["autonomous_start_requested"] is True
    assert result["task_executed"] is False
    assert result["direct_dispatch_requested"] is False


def test_1773_launch_denies_emergency_stop_active(tmp_path: Path) -> None:
    service = RuntimeOperatorService(_config(tmp_path))
    service.request_emergency_stop()

    result = service.run_goal("demo goal")

    assert result["ok"] is False
    assert result["launch_admitted"] is False
    assert result["denial_reason"] == "emergency_stop_active"
    assert result["status"]["emergency_stop_active"] is True


def test_1776_launch_denies_invalid_config(tmp_path: Path) -> None:
    config = RuntimeOperatorConfig(
        runtime_mode="invalid",
        max_tick_limit=0,
        checkpoint_path=str(tmp_path / "checkpoint.json"),
    )

    request = build_runtime_session_launch_request("demo goal", config)
    admission = evaluate_session_launch_admission(request)

    assert request["config_validation"]["config_valid"] is False
    assert "invalid_runtime_mode" in request["config_validation"]["problems"]
    assert "invalid_max_tick_limit" in request["config_validation"]["problems"]
    assert admission["launch_admitted"] is False
    assert admission["denial_reason"] == "invalid_runtime_mode"


def test_1779_manual_launch_requires_explicit_manual_mode(tmp_path: Path) -> None:
    denied = launch_goal_session("manual goal", _config(tmp_path, runtime_mode="manual"))
    admitted = launch_goal_session(
        "manual goal",
        _config(tmp_path, runtime_mode="manual"),
        explicit_manual_mode=True,
    )

    assert denied["launch_admitted"] is False
    assert denied["denial_reason"] == "manual_mode_requires_explicit_launch"
    assert admitted["launch_admitted"] is True
    assert admitted["autonomous_start_requested"] is False


def test_1782_operator_service_run_goal_updates_session_without_task_execution(tmp_path: Path) -> None:
    service = RuntimeOperatorService(_config(tmp_path))

    result = service.run_goal("demo goal")

    assert result["ok"] is True
    assert result["launch_admitted"] is True
    assert result["autonomous_start_requested"] is True
    assert result["runtime_session_id"]
    assert result["status"]["active"] is True
    assert result["status"]["controller_started"] is True
    assert result["runtime_state_mutated"] is False
    assert result["task_executed"] is False
    assert result["direct_dispatch_requested"] is False


def test_1785_cli_run_returns_deterministic_json_like_output(tmp_path: Path, capsys) -> None:
    checkpoint = str(tmp_path / "cli-run-checkpoint.json")

    first_code = zero_runtime_main(["--checkpoint-path", checkpoint, "run", "demo goal"])
    first = json.loads(capsys.readouterr().out)
    second_code = zero_runtime_main(["--checkpoint-path", checkpoint, "run", "demo goal"])
    second = json.loads(capsys.readouterr().out)

    assert first_code == 0
    assert second_code == 0
    for key in (
        "goal_id",
        "work_package_id",
        "runtime_session_id",
        "launch_admitted",
        "autonomous_start_requested",
    ):
        assert key in first
        assert first[key] == second[key]
    assert first["launch_admitted"] is True


def test_1792_goal_launch_boundary_scan() -> None:
    files = [
        Path("core/runtime/runtime_goal_intake.py"),
        Path("core/runtime/runtime_goal_session_launcher.py"),
        Path("core/runtime/runtime_operator_service.py"),
        Path("cli/zero_runtime_cli.py"),
    ]
    forbidden = [
        "import executor",
        "from executor",
        "scheduler.run",
        "run_one_step",
        "task_runner",
        "agent_loop",
        "progress_memory",
        ".run(",
    ]

    for file in files:
        source = file.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in source, f"{token!r} is contained in {file}"
