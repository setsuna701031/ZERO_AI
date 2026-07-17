from __future__ import annotations

import json
from pathlib import Path

from cli.zero_runtime_cli import main as zero_runtime_main
from core.runtime.runtime_autonomous_cycle_binding import bind_worker_pickup_to_cycle
from core.runtime.runtime_autonomous_cycle_execution_bridge import (
    bridge_cycle_binding_to_execution_request,
)
from core.runtime.runtime_controlled_action_proposal import (
    build_controlled_action_proposal_request,
    evaluate_controlled_action_proposal_admission,
    propose_controlled_action,
)
from core.runtime.runtime_controlled_loop_activation import activate_controlled_loop_tick
from core.runtime.runtime_controlled_tick_decision import decide_controlled_tick
from core.runtime.runtime_goal_queue_admission import submit_goal_session_to_queue
from core.runtime.runtime_goal_session_launcher import launch_goal_session
from core.runtime.runtime_operator_service import RuntimeOperatorService
from core.runtime.runtime_queue_worker_pickup import submit_queue_entry_for_worker_pickup


def _config(tmp_path: Path, **overrides):
    data = {
        "runtime_mode": "autonomous",
        "max_tick_limit": 3,
        "checkpoint_path": str(tmp_path / "action-proposal-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _decision(tmp_path: Path, goal: str = "action proposal"):
    launch = launch_goal_session(goal, _config(tmp_path))
    queued = submit_goal_session_to_queue(launch)
    pickup = submit_queue_entry_for_worker_pickup(queued["queue_entry"])
    cycle = bind_worker_pickup_to_cycle(pickup["worker_pickup_record"])
    bridge = bridge_cycle_binding_to_execution_request(cycle["cycle_binding"])
    loop = activate_controlled_loop_tick(bridge["execution_request"])
    decision = decide_controlled_tick(loop["controlled_loop_tick"])
    return decision["controlled_tick_decision"]


def test_1985_valid_decision_creates_proposal(tmp_path: Path) -> None:
    decision = _decision(tmp_path)
    result = propose_controlled_action(decision)

    assert result["ok"] is True
    assert result["action_proposed"] is True
    assert result["proposal_status"] == "action_proposed"
    assert result["proposal_id"]
    assert result["goal_id"] == decision["goal_id"]
    assert result["runtime_session_id"] == decision["runtime_session_id"]
    assert result["queue_entry_id"] == decision["queue_entry_id"]
    assert result["worker_claim_id"] == decision["worker_claim_id"]
    assert result["cycle_binding_id"] == decision["cycle_binding_id"]
    assert result["execution_request_id"] == decision["execution_request_id"]
    assert result["tick_id"] == decision["tick_id"]
    assert result["decision_id"] == decision["decision_id"]
    assert result["action_metadata"]["execution_permitted"] is False
    assert result["action_metadata"]["mutation_permitted"] is False


def test_1989_missing_decision_rejected() -> None:
    request = build_controlled_action_proposal_request(None)
    admission = evaluate_controlled_action_proposal_admission(request)

    assert request["proposal_request_created"] is False
    assert request["proposal_status"] == "rejected"
    assert request["denial_reason"] == "missing_controlled_tick_decision"
    assert admission["proposal_admitted"] is False
    assert admission["proposal_status"] == "rejected"
    assert admission["denial_reason"] == "missing_controlled_tick_decision"


def test_1993_rejected_decision_rejected(tmp_path: Path) -> None:
    decision = _decision(tmp_path)
    decision["decision_admitted"] = False
    decision["decision_status"] = "rejected"
    decision["denial_reason"] = "blocked_decision"

    result = propose_controlled_action(decision)

    assert result["action_proposed"] is False
    assert result["proposal_status"] == "rejected"
    assert result["denial_reason"] == "blocked_decision"


def test_1997_duplicate_proposal_rejected(tmp_path: Path) -> None:
    decision = _decision(tmp_path)
    first = propose_controlled_action(decision)
    second = propose_controlled_action(
        decision,
        existing_proposals=first["proposals"],
    )

    assert first["action_proposed"] is True
    assert second["action_proposed"] is False
    assert second["proposal_status"] == "rejected"
    assert second["denial_reason"] == "duplicate_action_proposal"
    assert second["proposal_count"] == 1


def test_2001_lineage_mismatch_rejected(tmp_path: Path) -> None:
    decision = _decision(tmp_path)
    decision["lineage"] = dict(decision["lineage"])
    decision["lineage"]["execution_request_id"] = "wrong-execution"

    result = propose_controlled_action(decision)

    assert result["action_proposed"] is False
    assert result["proposal_status"] == "rejected"
    assert result["denial_reason"] == "invalid_lineage"


def test_2005_lineage_preserved(tmp_path: Path) -> None:
    decision = _decision(tmp_path, "proposal lineage")
    result = propose_controlled_action(decision)
    proposal = result["action_proposal"]

    assert proposal["lineage"] == {
        "goal_id": decision["goal_id"],
        "work_package_id": decision["work_package_id"],
        "runtime_session_id": decision["runtime_session_id"],
        "queue_entry_id": decision["queue_entry_id"],
        "worker_claim_id": decision["worker_claim_id"],
        "cycle_binding_id": decision["cycle_binding_id"],
        "execution_request_id": decision["execution_request_id"],
        "tick_id": decision["tick_id"],
        "decision_id": decision["decision_id"],
    }


def test_2009_proposal_does_not_execute_anything(tmp_path: Path, capsys) -> None:
    service = RuntimeOperatorService(_config(tmp_path))
    result = service.run_goal("operator action proposal")
    status = service.status()

    assert result["proposal_status"] == "action_proposed"
    assert result["action_proposed"] is True
    assert result["action_proposal"]["proposal_admitted"] is True
    assert result["task_executed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["direct_dispatch_requested"] is False
    assert result["action_proposal"]["runtime_executed"] is False
    assert result["action_proposal"]["filesystem_mutated"] is False
    assert result["action_proposal"]["code_mutated"] is False
    assert result["action_proposal"]["cursor_advanced"] is False
    assert result["action_proposal"]["progress_memory_written"] is False
    assert status["proposal_status"]["proposal_status"] == "action_proposed"

    code = zero_runtime_main(
        ["--checkpoint-path", str(tmp_path / "cli-proposal.json"), "run", "task"]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert output["queue_status"] == "queued"
    assert output["worker_status"] == "claimed"
    assert output["cycle_status"] == "bound"
    assert output["execution_status"] == "ready"
    assert output["loop_status"] == "tick_created"
    assert output["decision_status"] == "decision_ready"
    assert output["proposal_status"] == "action_proposed"
    assert output["action_proposal"]["runtime_executed"] is False


def test_2016_forbidden_runtime_surface_scan() -> None:
    files = [
        Path("core/runtime/runtime_controlled_action_proposal.py"),
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
        "subprocess",
        "advance_cursor",
        "progress_memory.write",
        "write_text(",
        "remove_item",
        ".run(",
    ]

    for file in files:
        source = file.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in source, f"{token!r} is contained in {file}"
