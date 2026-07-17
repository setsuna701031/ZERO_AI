from __future__ import annotations

import json
from pathlib import Path

from cli.zero_runtime_cli import main as zero_runtime_main
from core.runtime.runtime_autonomous_cycle_binding import bind_worker_pickup_to_cycle
from core.runtime.runtime_autonomous_cycle_execution_bridge import (
    bridge_cycle_binding_to_execution_request,
)
from core.runtime.runtime_controlled_loop_activation import (
    activate_controlled_loop_tick,
    build_controlled_loop_tick_request,
    evaluate_controlled_loop_tick_admission,
)
from core.runtime.runtime_goal_queue_admission import submit_goal_session_to_queue
from core.runtime.runtime_goal_session_launcher import launch_goal_session
from core.runtime.runtime_operator_service import RuntimeOperatorService
from core.runtime.runtime_queue_worker_pickup import submit_queue_entry_for_worker_pickup


def _config(tmp_path: Path, **overrides):
    data = {
        "runtime_mode": "autonomous",
        "max_tick_limit": 3,
        "checkpoint_path": str(tmp_path / "loop-activation-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _execution_request(tmp_path: Path, goal: str = "loop activation"):
    launch = launch_goal_session(goal, _config(tmp_path))
    queued = submit_goal_session_to_queue(launch)
    pickup = submit_queue_entry_for_worker_pickup(queued["queue_entry"])
    cycle = bind_worker_pickup_to_cycle(pickup["worker_pickup_record"])
    bridge = bridge_cycle_binding_to_execution_request(cycle["cycle_binding"])
    return bridge["execution_request"]


def test_1921_ready_execution_creates_tick(tmp_path: Path) -> None:
    request = _execution_request(tmp_path)
    result = activate_controlled_loop_tick(request)

    assert result["ok"] is True
    assert result["tick_created"] is True
    assert result["loop_status"] == "tick_created"
    assert result["tick_status"] == "tick_created"
    assert result["tick_id"]
    assert result["tick_count"] == 1
    assert result["goal_id"] == request["goal_id"]
    assert result["runtime_session_id"] == request["runtime_session_id"]
    assert result["execution_request_id"] == request["execution_request_id"]
    assert result["controlled_loop_tick"]["tick_number"] == 1
    assert result["task_executed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["cursor_mutated"] is False
    assert result["loop_started"] is False
    assert result["progress_memory_written"] is False


def test_1925_rejected_execution_blocked(tmp_path: Path) -> None:
    request = _execution_request(tmp_path)
    request["execution_status"] = "rejected"

    result = activate_controlled_loop_tick(request)

    assert result["tick_created"] is False
    assert result["loop_status"] == "blocked"
    assert result["tick_status"] == "blocked"
    assert result["denial_reason"] == "rejected_execution_request"


def test_1929_missing_execution_request_blocked() -> None:
    tick_request = build_controlled_loop_tick_request(None)
    admission = evaluate_controlled_loop_tick_admission(tick_request)

    assert tick_request["tick_request_created"] is False
    assert tick_request["tick_status"] == "blocked"
    assert tick_request["denial_reason"] == "missing_execution_request"
    assert admission["tick_admitted"] is False
    assert admission["tick_status"] == "blocked"
    assert admission["denial_reason"] == "missing_execution_request"


def test_1933_duplicate_tick_denied(tmp_path: Path) -> None:
    request = _execution_request(tmp_path)
    first = activate_controlled_loop_tick(request)
    second = activate_controlled_loop_tick(request, existing_ticks=first["ticks"])

    assert first["tick_created"] is True
    assert second["tick_created"] is False
    assert second["loop_status"] == "blocked"
    assert second["denial_reason"] == "duplicate_tick"
    assert second["tick_count"] == 1


def test_1937_lineage_preserved(tmp_path: Path) -> None:
    request = _execution_request(tmp_path, "loop lineage")
    result = activate_controlled_loop_tick(request)
    tick = result["controlled_loop_tick"]

    assert tick["lineage"] == {
        "goal_id": request["goal_id"],
        "work_package_id": request["work_package_id"],
        "runtime_session_id": request["runtime_session_id"],
        "queue_entry_id": request["queue_entry_id"],
        "worker_claim_id": request["worker_claim_id"],
        "cycle_binding_id": request["cycle_binding_id"],
        "execution_request_id": request["execution_request_id"],
    }
    assert tick["autonomous_cycle_state"]["goal_id"] == request["goal_id"]
    assert tick["autonomous_cycle_state"]["runtime_session_id"] == request[
        "runtime_session_id"
    ]
    assert tick["autonomous_cycle_state"]["execution_request_id"] == request[
        "execution_request_id"
    ]


def test_1941_invalid_lineage_blocked(tmp_path: Path) -> None:
    request = _execution_request(tmp_path)
    request["lineage"] = dict(request["lineage"])
    request["lineage"]["cycle_binding_id"] = "wrong-binding"

    result = activate_controlled_loop_tick(request)

    assert result["tick_created"] is False
    assert result["loop_status"] == "blocked"
    assert result["denial_reason"] == "invalid_lineage"


def test_1945_operator_exposes_loop_status(tmp_path: Path) -> None:
    service = RuntimeOperatorService(_config(tmp_path))

    result = service.run_goal("operator loop activation")
    status = service.status()

    assert result["loop_status"] == "tick_created"
    assert result["tick_status"] == "tick_created"
    assert result["controlled_loop_tick"]["tick_admitted"] is True
    assert status["loop_status"]["loop_status"] == "tick_created"
    assert status["loop_status"]["created_count"] == 1
    assert status["loop_status"]["created_execution_request_ids"] == [
        result["execution_request"]["execution_request_id"]
    ]


def test_1949_cli_exposes_loop_status(tmp_path: Path, capsys) -> None:
    code = zero_runtime_main(
        ["--checkpoint-path", str(tmp_path / "cli-loop.json"), "run", "task"]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert output["queue_status"] == "queued"
    assert output["worker_status"] == "claimed"
    assert output["cycle_status"] == "bound"
    assert output["execution_status"] == "ready"
    assert output["loop_status"] == "tick_created"
    assert output["controlled_loop_tick"]["tick_admitted"] is True


def test_1952_no_forbidden_runtime_bypass() -> None:
    files = [
        Path("core/runtime/runtime_controlled_loop_activation.py"),
        Path("core/runtime/runtime_operator_service.py"),
        Path("cli/zero_runtime_cli.py"),
    ]
    forbidden = [
        "while true",
        "subprocess",
        "scheduler.run",
        "run_one_step",
        "task_runner",
        "agent_loop",
        "progress_memory.write",
        "advance_cursor",
        ".run(",
    ]

    for file in files:
        source = file.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in source, f"{token!r} is contained in {file}"
