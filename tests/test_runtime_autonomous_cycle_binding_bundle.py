from __future__ import annotations

import json
from pathlib import Path

from cli.zero_runtime_cli import main as zero_runtime_main
from core.runtime.runtime_autonomous_cycle_binding import (
    adapt_worker_pickup_to_cycle_request,
    bind_worker_pickup_to_cycle,
    evaluate_autonomous_cycle_admission,
)
from core.runtime.runtime_goal_queue_admission import submit_goal_session_to_queue
from core.runtime.runtime_goal_session_launcher import launch_goal_session
from core.runtime.runtime_operator_service import RuntimeOperatorService
from core.runtime.runtime_queue_worker_pickup import submit_queue_entry_for_worker_pickup


def _config(tmp_path: Path, **overrides):
    data = {
        "runtime_mode": "autonomous",
        "max_tick_limit": 3,
        "checkpoint_path": str(tmp_path / "cycle-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _pickup_record(tmp_path: Path, goal: str = "bind cycle"):
    launch = launch_goal_session(goal, _config(tmp_path))
    queued = submit_goal_session_to_queue(launch)
    pickup = submit_queue_entry_for_worker_pickup(queued["queue_entry"])
    return pickup["worker_pickup_record"]


def test_1857_valid_claimed_worker_pickup_creates_cycle_binding(tmp_path: Path) -> None:
    pickup = _pickup_record(tmp_path)
    result = bind_worker_pickup_to_cycle(pickup)

    assert result["ok"] is True
    assert result["bound"] is True
    assert result["cycle_status"] == "bound"
    assert result["goal_id"] == pickup["goal_id"]
    assert result["work_package_id"] == pickup["work_package_id"]
    assert result["runtime_session_id"] == pickup["runtime_session_id"]
    assert result["queue_entry_id"] == pickup["queue_entry_id"]
    assert result["worker_claim_id"] == pickup["worker_claim_id"]
    assert result["task_executed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["cursor_mutated"] is False
    assert result["loop_started"] is False


def test_1861_missing_pickup_record_denied() -> None:
    request = adapt_worker_pickup_to_cycle_request(None)
    admission = evaluate_autonomous_cycle_admission(request)

    assert request["cycle_request_created"] is False
    assert request["denial_reason"] == "missing_worker_pickup_record"
    assert admission["cycle_binding_admitted"] is False
    assert admission["cycle_status"] == "denied"
    assert admission["denial_reason"] == "missing_worker_pickup_record"


def test_1865_unclaimed_pickup_denied(tmp_path: Path) -> None:
    pickup = _pickup_record(tmp_path)
    pickup["worker_pickup_admitted"] = False
    pickup["worker_pickup_status"] = "denied"
    pickup["denial_reason"] = "not_claimed"

    result = bind_worker_pickup_to_cycle(pickup)

    assert result["bound"] is False
    assert result["cycle_status"] == "denied"
    assert result["denial_reason"] == "not_claimed"


def test_1869_invalid_lineage_denied(tmp_path: Path) -> None:
    pickup = _pickup_record(tmp_path)
    pickup["lineage"] = dict(pickup["lineage"])
    pickup["lineage"]["work_package_id"] = "wrong-work"

    result = bind_worker_pickup_to_cycle(pickup)

    assert result["bound"] is False
    assert result["denial_reason"] == "invalid_lineage"


def test_1873_duplicate_cycle_binding_denied(tmp_path: Path) -> None:
    pickup = _pickup_record(tmp_path)
    first = bind_worker_pickup_to_cycle(pickup)
    second = bind_worker_pickup_to_cycle(pickup, existing_bindings=first["bindings"])

    assert first["bound"] is True
    assert second["bound"] is False
    assert second["denial_reason"] == "duplicate_cycle_binding"
    assert second["binding_count"] == 1


def test_1877_cycle_context_preserves_lineage(tmp_path: Path) -> None:
    pickup = _pickup_record(tmp_path, "cycle lineage")
    result = bind_worker_pickup_to_cycle(pickup)
    binding = result["cycle_binding"]

    assert binding["lineage"] == {
        "goal_id": pickup["goal_id"],
        "work_package_id": pickup["work_package_id"],
        "runtime_session_id": pickup["runtime_session_id"],
        "queue_entry_id": pickup["queue_entry_id"],
        "worker_claim_id": pickup["worker_claim_id"],
    }


def test_1881_operator_status_shows_cycle_bound(tmp_path: Path) -> None:
    service = RuntimeOperatorService(_config(tmp_path))

    result = service.run_goal("operator cycle")
    status = service.status()

    assert result["cycle_status"] == "bound"
    assert result["cycle_bound"] is True
    assert result["cycle_binding"]["cycle_binding_admitted"] is True
    assert status["cycle_status"]["cycle_status"] == "bound"
    assert status["cycle_status"]["bound_count"] == 1
    assert status["cycle_status"]["bound_runtime_session_ids"] == [result["runtime_session_id"]]


def test_1885_cli_exposes_cycle_status(tmp_path: Path, capsys) -> None:
    code = zero_runtime_main(
        ["--checkpoint-path", str(tmp_path / "cli-cycle.json"), "run", "task"]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert output["queued"] is True
    assert output["claimed"] is True
    assert output["cycle_status"] == "bound"
    assert output["cycle_bound"] is True
    assert output["cycle_binding"]["cycle_binding_admitted"] is True


def test_1888_cycle_binding_boundary_scan() -> None:
    files = [
        Path("core/runtime/runtime_autonomous_cycle_binding.py"),
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
        "subprocess",
        ".run(",
    ]

    for file in files:
        source = file.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in source, f"{token!r} is contained in {file}"
