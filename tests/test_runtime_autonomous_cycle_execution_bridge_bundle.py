from __future__ import annotations

import json
from pathlib import Path

from cli.zero_runtime_cli import main as zero_runtime_main
from core.runtime.runtime_autonomous_cycle_binding import bind_worker_pickup_to_cycle
from core.runtime.runtime_autonomous_cycle_execution_bridge import (
    bridge_cycle_binding_to_execution_request,
    build_cycle_execution_request,
    evaluate_cycle_execution_admission,
)
from core.runtime.runtime_goal_queue_admission import submit_goal_session_to_queue
from core.runtime.runtime_goal_session_launcher import launch_goal_session
from core.runtime.runtime_operator_service import RuntimeOperatorService
from core.runtime.runtime_queue_worker_pickup import submit_queue_entry_for_worker_pickup


def _config(tmp_path: Path, **overrides):
    data = {
        "runtime_mode": "autonomous",
        "max_tick_limit": 3,
        "checkpoint_path": str(tmp_path / "execution-bridge-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _cycle_binding(tmp_path: Path, goal: str = "execution bridge"):
    launch = launch_goal_session(goal, _config(tmp_path))
    queued = submit_goal_session_to_queue(launch)
    pickup = submit_queue_entry_for_worker_pickup(queued["queue_entry"])
    cycle = bind_worker_pickup_to_cycle(pickup["worker_pickup_record"])
    return cycle["cycle_binding"]


def test_1889_valid_cycle_creates_execution_request(tmp_path: Path) -> None:
    binding = _cycle_binding(tmp_path)
    result = bridge_cycle_binding_to_execution_request(binding)

    assert result["ok"] is True
    assert result["execution_ready"] is True
    assert result["execution_status"] == "ready"
    assert result["goal_id"] == binding["goal_id"]
    assert result["runtime_session_id"] == binding["runtime_session_id"]
    assert result["queue_entry_id"] == binding["queue_entry_id"]
    assert result["worker_claim_id"] == binding["worker_claim_id"]
    assert result["cycle_binding_id"] == binding["cycle_binding_id"]
    assert result["execution_request"]["execution_request_admitted"] is True
    assert result["execution_request_count"] == 1
    assert result["task_executed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["cursor_advanced"] is False
    assert result["loop_started"] is False
    assert result["progress_memory_written"] is False


def test_1893_missing_cycle_rejected() -> None:
    request = build_cycle_execution_request(None)
    admission = evaluate_cycle_execution_admission(request)

    assert request["execution_request_created"] is False
    assert request["execution_status"] == "rejected"
    assert request["denial_reason"] == "missing_cycle_binding"
    assert admission["execution_request_admitted"] is False
    assert admission["execution_status"] == "rejected"
    assert admission["denial_reason"] == "missing_cycle_binding"


def test_1897_unbound_cycle_rejected(tmp_path: Path) -> None:
    binding = _cycle_binding(tmp_path)
    binding["cycle_status"] = "denied"

    result = bridge_cycle_binding_to_execution_request(binding)

    assert result["execution_ready"] is False
    assert result["execution_status"] == "rejected"
    assert result["denial_reason"] == "cycle_not_bound"


def test_1901_duplicate_execution_request_denied(tmp_path: Path) -> None:
    binding = _cycle_binding(tmp_path)
    first = bridge_cycle_binding_to_execution_request(binding)
    second = bridge_cycle_binding_to_execution_request(
        binding,
        existing_requests=first["execution_requests"],
    )

    assert first["execution_ready"] is True
    assert second["execution_ready"] is False
    assert second["execution_status"] == "rejected"
    assert second["denial_reason"] == "duplicate_execution_request"
    assert second["execution_request_count"] == 1


def test_1905_lineage_preserved(tmp_path: Path) -> None:
    binding = _cycle_binding(tmp_path, "execution lineage")
    result = bridge_cycle_binding_to_execution_request(binding)
    request = result["execution_request"]

    assert request["lineage"] == {
        "goal_id": binding["goal_id"],
        "work_package_id": binding["work_package_id"],
        "runtime_session_id": binding["runtime_session_id"],
        "queue_entry_id": binding["queue_entry_id"],
        "worker_claim_id": binding["worker_claim_id"],
        "cycle_binding_id": binding["cycle_binding_id"],
    }
    assert request["controlled_loop_input"]["goal_id"] == binding["goal_id"]
    assert request["controlled_loop_input"]["runtime_session_id"] == binding[
        "runtime_session_id"
    ]
    assert request["controlled_loop_input"]["queue_entry_id"] == binding[
        "queue_entry_id"
    ]
    assert request["controlled_loop_input"]["worker_claim_id"] == binding[
        "worker_claim_id"
    ]
    assert request["controlled_loop_input"]["cycle_binding_id"] == binding[
        "cycle_binding_id"
    ]


def test_1909_invalid_lineage_rejected(tmp_path: Path) -> None:
    binding = _cycle_binding(tmp_path)
    binding["lineage"] = dict(binding["lineage"])
    binding["lineage"]["runtime_session_id"] = "wrong-session"

    result = bridge_cycle_binding_to_execution_request(binding)

    assert result["execution_ready"] is False
    assert result["execution_status"] == "rejected"
    assert result["denial_reason"] == "invalid_lineage"


def test_1913_operator_exposes_execution_status(tmp_path: Path) -> None:
    service = RuntimeOperatorService(_config(tmp_path))

    result = service.run_goal("operator execution bridge")
    status = service.status()

    assert result["execution_status"] == "ready"
    assert result["execution_ready"] is True
    assert result["execution_request"]["execution_request_admitted"] is True
    assert status["execution_status"]["execution_status"] == "ready"
    assert status["execution_status"]["ready_count"] == 1
    assert status["execution_status"]["ready_runtime_session_ids"] == [
        result["runtime_session_id"]
    ]


def test_1917_cli_exposes_execution_status(tmp_path: Path, capsys) -> None:
    code = zero_runtime_main(
        ["--checkpoint-path", str(tmp_path / "cli-execution.json"), "run", "task"]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert output["queue_status"] == "queued"
    assert output["worker_pickup_status"] == "claimed"
    assert output["cycle_status"] == "bound"
    assert output["execution_status"] == "ready"
    assert output["execution_ready"] is True
    assert output["execution_request"]["execution_request_admitted"] is True


def test_1920_boundary_scan_prevents_forbidden_execution_bypass() -> None:
    files = [
        Path("core/runtime/runtime_autonomous_cycle_execution_bridge.py"),
        Path("core/runtime/runtime_operator_service.py"),
        Path("cli/zero_runtime_cli.py"),
    ]
    forbidden = [
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
