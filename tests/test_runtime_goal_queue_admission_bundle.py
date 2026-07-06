from __future__ import annotations

import json
from pathlib import Path

from cli.zero_runtime_cli import main as zero_runtime_main
from core.runtime.runtime_goal_queue_admission import (
    build_queue_state,
    build_session_queue_entry,
    evaluate_goal_queue_admission,
    submit_goal_session_to_queue,
)
from core.runtime.runtime_goal_session_launcher import launch_goal_session
from core.runtime.runtime_operator_service import RuntimeOperatorService


def _config(tmp_path: Path, **overrides):
    data = {
        "runtime_mode": "autonomous",
        "max_tick_limit": 3,
        "checkpoint_path": str(tmp_path / "queue-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _launch(tmp_path: Path, goal: str = "queue this task"):
    return launch_goal_session(goal, _config(tmp_path))


def test_1793_valid_session_enters_queue(tmp_path: Path) -> None:
    launch = _launch(tmp_path)
    result = submit_goal_session_to_queue(launch)

    assert result["ok"] is True
    assert result["queued"] is True
    assert result["queue_status"] == "queued"
    assert result["queue_depth"] == 1
    assert result["goal_id"] == launch["goal_id"]
    assert result["work_package_id"] == launch["work_package_id"]
    assert result["runtime_session_id"] == launch["runtime_session_id"]
    assert result["task_executed"] is False
    assert result["direct_dispatch_requested"] is False
    assert result["runtime_state_mutated"] is False


def test_1797_invalid_session_denied(tmp_path: Path) -> None:
    launch = _launch(tmp_path)
    launch["launch_admitted"] = False
    launch["runtime_session_id"] = ""
    launch["denial_reason"] = "launch_not_admitted"

    entry = build_session_queue_entry(launch)
    admission = evaluate_goal_queue_admission(entry)

    assert entry["queue_entry_created"] is False
    assert admission["queue_admitted"] is False
    assert admission["denial_reason"] == "launch_not_admitted"


def test_1801_duplicate_session_denied(tmp_path: Path) -> None:
    launch = _launch(tmp_path)
    first = submit_goal_session_to_queue(launch)
    second = submit_goal_session_to_queue(launch, existing_queue=first["queue_entries"])

    assert first["queued"] is True
    assert second["queued"] is False
    assert second["denial_reason"] == "duplicate_runtime_session"
    assert second["queue_depth"] == 1


def test_1805_lineage_preserved_from_goal_to_queue(tmp_path: Path) -> None:
    launch = _launch(tmp_path, "preserve lineage")
    result = submit_goal_session_to_queue(launch)
    entry = result["queue_entry"]

    assert entry["lineage"] == {
        "goal_id": launch["goal_id"],
        "work_package_id": launch["work_package_id"],
        "runtime_session_id": launch["runtime_session_id"],
    }
    assert result["queue_admission"]["lineage"] == entry["lineage"]


def test_1809_operator_queue_submit_and_visibility(tmp_path: Path) -> None:
    service = RuntimeOperatorService(_config(tmp_path))

    result = service.run_goal("operator queue goal")
    status = service.status()
    queue_status = service.queue_status()

    assert result["ok"] is True
    assert result["queued"] is True
    assert result["queue_status"] == "queued"
    assert result["queue_admission"]["queue_admitted"] is True
    assert status["queue_status"]["queue_depth"] == 1
    assert queue_status["queued_runtime_session_ids"] == [result["runtime_session_id"]]


def test_1813_operator_duplicate_queue_submit_denied(tmp_path: Path) -> None:
    service = RuntimeOperatorService(_config(tmp_path))

    first = service.run_goal("same goal")
    second = service.run_goal("same goal")

    assert first["queued"] is True
    assert second["queued"] is False
    assert second["ok"] is False
    assert second["denial_reason"] == "duplicate_runtime_session"
    assert service.queue_status()["queue_depth"] == 1


def test_1817_queue_state_visibility_is_deterministic(tmp_path: Path) -> None:
    launch = _launch(tmp_path, "visible queue")
    submit = submit_goal_session_to_queue(launch)

    first = build_queue_state(submit["queue_entries"])
    second = build_queue_state(submit["queue_entries"])

    assert first == second
    assert first["queue_depth"] == 1
    assert first["queued_work_package_ids"] == [launch["work_package_id"]]
    assert first["task_executed"] is False


def test_1820_cli_run_exposes_queued_status(tmp_path: Path, capsys) -> None:
    code = zero_runtime_main(
        ["--checkpoint-path", str(tmp_path / "cli-queue.json"), "run", "task"]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert output["launch_admitted"] is True
    assert output["queued"] is True
    assert output["queue_status"] == "queued"
    assert output["queue_admission"]["queue_admitted"] is True


def test_1824_goal_queue_boundary_scan() -> None:
    files = [
        Path("core/runtime/runtime_goal_queue_admission.py"),
        Path("core/runtime/runtime_goal_session_launcher.py"),
        Path("core/runtime/runtime_operator_service.py"),
        Path("cli/zero_runtime_cli.py"),
    ]
    forbidden = [
        "executor",
        "task_runner",
        "run_one_step",
        "agent_loop",
    ]

    for file in files:
        source = file.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in source, f"{token!r} is contained in {file}"
