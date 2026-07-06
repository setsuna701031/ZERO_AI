from __future__ import annotations

import json
from pathlib import Path

from cli.zero_runtime_cli import main as zero_runtime_main
from core.runtime.runtime_goal_queue_admission import submit_goal_session_to_queue
from core.runtime.runtime_goal_session_launcher import launch_goal_session
from core.runtime.runtime_operator_service import RuntimeOperatorService
from core.runtime.runtime_queue_worker_pickup import (
    adapt_queue_entry_to_work_claim,
    evaluate_worker_pickup_admission,
    submit_queue_entry_for_worker_pickup,
)


def _config(tmp_path: Path, **overrides):
    data = {
        "runtime_mode": "autonomous",
        "max_tick_limit": 3,
        "checkpoint_path": str(tmp_path / "pickup-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _queue_entry(tmp_path: Path, goal: str = "pickup task"):
    launch = launch_goal_session(goal, _config(tmp_path))
    queued = submit_goal_session_to_queue(launch)
    return queued["queue_entry"]


def test_1825_valid_queue_entry_can_be_claimed(tmp_path: Path) -> None:
    entry = _queue_entry(tmp_path)
    result = submit_queue_entry_for_worker_pickup(entry)

    assert result["ok"] is True
    assert result["claimed"] is True
    assert result["worker_pickup_status"] == "claimed"
    assert result["queue_entry"]["queue_status"] == "claimed"
    assert result["goal_id"] == entry["goal_id"]
    assert result["work_package_id"] == entry["work_package_id"]
    assert result["runtime_session_id"] == entry["runtime_session_id"]
    assert result["queue_entry_id"] == entry["queue_entry_id"]
    assert result["task_executed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["cursor_mutated"] is False


def test_1829_missing_queue_entry_denied() -> None:
    claim = adapt_queue_entry_to_work_claim(None)
    admission = evaluate_worker_pickup_admission(claim)

    assert claim["work_claim_created"] is False
    assert claim["denial_reason"] == "missing_queue_entry"
    assert admission["worker_pickup_admitted"] is False
    assert admission["denial_reason"] == "missing_queue_entry"


def test_1833_non_admitted_queue_entry_denied(tmp_path: Path) -> None:
    entry = _queue_entry(tmp_path)
    entry["queue_entry_created"] = False
    entry["denial_reason"] = "queue_not_admitted"

    result = submit_queue_entry_for_worker_pickup(entry)

    assert result["claimed"] is False
    assert result["denial_reason"] == "queue_entry_not_admitted"


def test_1837_duplicate_claim_denied(tmp_path: Path) -> None:
    entry = _queue_entry(tmp_path)
    first = submit_queue_entry_for_worker_pickup(entry)
    second = submit_queue_entry_for_worker_pickup(entry, existing_claims=first["claims"])

    assert first["claimed"] is True
    assert second["claimed"] is False
    assert second["denial_reason"] == "duplicate_worker_claim"
    assert second["claim_count"] == 1


def test_1841_invalid_lineage_denied(tmp_path: Path) -> None:
    entry = _queue_entry(tmp_path)
    entry["lineage"] = dict(entry["lineage"])
    entry["lineage"]["goal_id"] = "wrong-goal"

    result = submit_queue_entry_for_worker_pickup(entry)

    assert result["claimed"] is False
    assert result["denial_reason"] == "invalid_lineage"


def test_1845_claim_preserves_lineage(tmp_path: Path) -> None:
    entry = _queue_entry(tmp_path, "lineage pickup")
    result = submit_queue_entry_for_worker_pickup(entry)
    record = result["worker_pickup_record"]

    assert record["lineage"] == {
        "goal_id": entry["goal_id"],
        "work_package_id": entry["work_package_id"],
        "runtime_session_id": entry["runtime_session_id"],
        "queue_entry_id": entry["queue_entry_id"],
    }


def test_1849_operator_queue_status_shows_claimed(tmp_path: Path) -> None:
    service = RuntimeOperatorService(_config(tmp_path))

    result = service.run_goal("operator pickup")
    status = service.queue_status()

    assert result["queued"] is True
    assert result["claimed"] is True
    assert result["worker_pickup_status"] == "claimed"
    assert status["queue_depth"] == 1
    assert status["claimed_count"] == 1
    assert status["claimed_runtime_session_ids"] == [result["runtime_session_id"]]
    assert status["entries"][0]["queue_status"] == "claimed"


def test_1853_cli_exposes_claimed_status(tmp_path: Path, capsys) -> None:
    code = zero_runtime_main(
        ["--checkpoint-path", str(tmp_path / "cli-pickup.json"), "run", "task"]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert output["queued"] is True
    assert output["queue_status"] == "queued"
    assert output["claimed"] is True
    assert output["worker_pickup_status"] == "claimed"
    assert output["worker_pickup"]["worker_pickup_admitted"] is True


def test_1856_worker_pickup_boundary_scan() -> None:
    files = [
        Path("core/runtime/runtime_queue_worker_pickup.py"),
        Path("core/runtime/runtime_operator_service.py"),
        Path("cli/zero_runtime_cli.py"),
    ]
    forbidden = [
        "executor",
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
