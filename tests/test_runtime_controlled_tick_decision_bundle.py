from __future__ import annotations

import json
from pathlib import Path

from cli.zero_runtime_cli import main as zero_runtime_main
from core.runtime.runtime_autonomous_cycle_binding import bind_worker_pickup_to_cycle
from core.runtime.runtime_autonomous_cycle_execution_bridge import (
    bridge_cycle_binding_to_execution_request,
)
from core.runtime.runtime_controlled_loop_activation import activate_controlled_loop_tick
from core.runtime.runtime_controlled_tick_decision import (
    build_controlled_tick_decision_request,
    decide_controlled_tick,
    evaluate_controlled_tick_decision_admission,
)
from core.runtime.runtime_goal_queue_admission import submit_goal_session_to_queue
from core.runtime.runtime_goal_session_launcher import launch_goal_session
from core.runtime.runtime_operator_service import RuntimeOperatorService
from core.runtime.runtime_queue_worker_pickup import submit_queue_entry_for_worker_pickup


def _config(tmp_path: Path, **overrides):
    data = {
        "runtime_mode": "autonomous",
        "max_tick_limit": 3,
        "checkpoint_path": str(tmp_path / "tick-decision-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _controlled_tick(tmp_path: Path, goal: str = "tick decision"):
    launch = launch_goal_session(goal, _config(tmp_path))
    queued = submit_goal_session_to_queue(launch)
    pickup = submit_queue_entry_for_worker_pickup(queued["queue_entry"])
    cycle = bind_worker_pickup_to_cycle(pickup["worker_pickup_record"])
    bridge = bridge_cycle_binding_to_execution_request(cycle["cycle_binding"])
    loop = activate_controlled_loop_tick(bridge["execution_request"])
    return loop["controlled_loop_tick"]


def test_1953_valid_tick_creates_decision(tmp_path: Path) -> None:
    tick = _controlled_tick(tmp_path)
    result = decide_controlled_tick(tick)

    assert result["ok"] is True
    assert result["decision_ready"] is True
    assert result["decision_status"] == "decision_ready"
    assert result["decision_id"]
    assert result["goal_id"] == tick["goal_id"]
    assert result["runtime_session_id"] == tick["runtime_session_id"]
    assert result["queue_entry_id"] == tick["queue_entry_id"]
    assert result["worker_claim_id"] == tick["worker_claim_id"]
    assert result["cycle_binding_id"] == tick["cycle_binding_id"]
    assert result["execution_request_id"] == tick["execution_request_id"]
    assert result["tick_id"] == tick["tick_id"]
    assert result["state_metadata"]["record_only"] is True
    assert result["task_executed"] is False
    assert result["runtime_executed"] is False
    assert result["cursor_advanced"] is False
    assert result["progress_memory_written"] is False


def test_1957_missing_tick_rejected() -> None:
    request = build_controlled_tick_decision_request(None)
    admission = evaluate_controlled_tick_decision_admission(request)

    assert request["decision_request_created"] is False
    assert request["decision_status"] == "rejected"
    assert request["denial_reason"] == "missing_controlled_loop_tick"
    assert admission["decision_admitted"] is False
    assert admission["decision_status"] == "rejected"
    assert admission["denial_reason"] == "missing_controlled_loop_tick"


def test_1961_duplicate_rejected(tmp_path: Path) -> None:
    tick = _controlled_tick(tmp_path)
    first = decide_controlled_tick(tick)
    second = decide_controlled_tick(tick, existing_decisions=first["decisions"])

    assert first["decision_ready"] is True
    assert second["decision_ready"] is False
    assert second["decision_status"] == "rejected"
    assert second["denial_reason"] == "duplicate_tick_decision"
    assert second["decision_count"] == 1


def test_1965_lineage_mismatch_rejected(tmp_path: Path) -> None:
    tick = _controlled_tick(tmp_path)
    tick["lineage"] = dict(tick["lineage"])
    tick["lineage"]["queue_entry_id"] = "wrong-queue"

    result = decide_controlled_tick(tick)

    assert result["decision_ready"] is False
    assert result["decision_status"] == "rejected"
    assert result["denial_reason"] == "invalid_lineage"


def test_1969_rejected_tick_rejected(tmp_path: Path) -> None:
    tick = _controlled_tick(tmp_path)
    tick["tick_admitted"] = False
    tick["tick_status"] = "blocked"
    tick["denial_reason"] = "blocked_tick"

    result = decide_controlled_tick(tick)

    assert result["decision_ready"] is False
    assert result["decision_status"] == "rejected"
    assert result["denial_reason"] == "blocked_tick"


def test_1973_lineage_preserved(tmp_path: Path) -> None:
    tick = _controlled_tick(tmp_path, "decision lineage")
    result = decide_controlled_tick(tick)
    decision = result["controlled_tick_decision"]

    assert decision["lineage"] == {
        "goal_id": tick["goal_id"],
        "work_package_id": tick["work_package_id"],
        "runtime_session_id": tick["runtime_session_id"],
        "queue_entry_id": tick["queue_entry_id"],
        "worker_claim_id": tick["worker_claim_id"],
        "cycle_binding_id": tick["cycle_binding_id"],
        "execution_request_id": tick["execution_request_id"],
        "tick_id": tick["tick_id"],
    }


def test_1977_operator_and_cli_expose_decision_status(tmp_path: Path, capsys) -> None:
    service = RuntimeOperatorService(_config(tmp_path))
    result = service.run_goal("operator tick decision")
    status = service.status()

    assert result["decision_status"] == "decision_ready"
    assert result["decision_ready"] is True
    assert result["controlled_tick_decision"]["decision_admitted"] is True
    assert status["decision_status"]["decision_status"] == "decision_ready"
    assert status["decision_status"]["ready_count"] == 1

    code = zero_runtime_main(
        ["--checkpoint-path", str(tmp_path / "cli-decision.json"), "run", "task"]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert output["queue_status"] == "queued"
    assert output["worker_status"] == "claimed"
    assert output["cycle_status"] == "bound"
    assert output["execution_status"] == "ready"
    assert output["loop_status"] == "tick_created"
    assert output["decision_status"] == "decision_ready"
    assert output["controlled_tick_decision"]["decision_admitted"] is True


def test_1984_no_forbidden_runtime_surface_tokens() -> None:
    files = [
        Path("core/runtime/runtime_controlled_tick_decision.py"),
        Path("core/runtime/runtime_operator_service.py"),
        Path("cli/zero_runtime_cli.py"),
    ]
    forbidden = [
        "from core.runtime.executor",
        "import executor",
        "from core.runtime.scheduler",
        "import scheduler",
        "task_runner",
        "agent_loop",
        "progress_memory.write",
        "advance_cursor",
        "subprocess",
        ".run(",
    ]

    for file in files:
        source = file.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in source, f"{token!r} is contained in {file}"
