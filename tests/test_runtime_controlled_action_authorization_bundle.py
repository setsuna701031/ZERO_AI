from __future__ import annotations

import json
from pathlib import Path

from cli.zero_runtime_cli import main as zero_runtime_main
from core.runtime.runtime_autonomous_cycle_binding import bind_worker_pickup_to_cycle
from core.runtime.runtime_autonomous_cycle_execution_bridge import (
    bridge_cycle_binding_to_execution_request,
)
from core.runtime.runtime_controlled_action_authorization import (
    authorize_controlled_action,
    build_controlled_action_authorization_request,
    evaluate_controlled_action_authorization_admission,
)
from core.runtime.runtime_controlled_action_proposal import propose_controlled_action
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
        "checkpoint_path": str(tmp_path / "action-authorization-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _proposal(tmp_path: Path, goal: str = "action authorization"):
    launch = launch_goal_session(goal, _config(tmp_path))
    queued = submit_goal_session_to_queue(launch)
    pickup = submit_queue_entry_for_worker_pickup(queued["queue_entry"])
    cycle = bind_worker_pickup_to_cycle(pickup["worker_pickup_record"])
    bridge = bridge_cycle_binding_to_execution_request(cycle["cycle_binding"])
    loop = activate_controlled_loop_tick(bridge["execution_request"])
    decision = decide_controlled_tick(loop["controlled_loop_tick"])
    proposal = propose_controlled_action(decision["controlled_tick_decision"])
    return proposal["action_proposal"]


def test_2017_valid_proposal_creates_authorization_record(tmp_path: Path) -> None:
    proposal = _proposal(tmp_path)
    result = authorize_controlled_action(proposal)

    assert result["ok"] is True
    assert result["authorization_status"] == "authorized"
    assert result["authorized"] is False
    assert result["authorization_id"]
    assert result["goal_id"] == proposal["goal_id"]
    assert result["runtime_session_id"] == proposal["runtime_session_id"]
    assert result["queue_entry_id"] == proposal["queue_entry_id"]
    assert result["worker_claim_id"] == proposal["worker_claim_id"]
    assert result["cycle_binding_id"] == proposal["cycle_binding_id"]
    assert result["execution_request_id"] == proposal["execution_request_id"]
    assert result["tick_id"] == proposal["tick_id"]
    assert result["decision_id"] == proposal["decision_id"]
    assert result["proposal_id"] == proposal["proposal_id"]
    assert result["approval_metadata"]["operator_approved"] is False
    assert result["safety_flags"]["execution_permitted"] is False


def test_2021_rejected_proposal_denied(tmp_path: Path) -> None:
    proposal = _proposal(tmp_path)
    proposal["proposal_admitted"] = False
    proposal["proposal_status"] = "rejected"
    proposal["denial_reason"] = "blocked_proposal"

    result = authorize_controlled_action(proposal)

    assert result["ok"] is False
    assert result["authorization_status"] == "denied"
    assert result["authorized"] is False
    assert result["denial_reason"] == "blocked_proposal"


def test_2025_missing_proposal_rejected() -> None:
    request = build_controlled_action_authorization_request(None)
    admission = evaluate_controlled_action_authorization_admission(request)

    assert request["authorization_request_created"] is False
    assert request["authorization_status"] == "denied"
    assert request["denial_reason"] == "missing_action_proposal"
    assert admission["authorization_admitted"] is False
    assert admission["authorization_status"] == "denied"
    assert admission["denial_reason"] == "missing_action_proposal"


def test_2029_duplicate_authorization_rejected(tmp_path: Path) -> None:
    proposal = _proposal(tmp_path)
    first = authorize_controlled_action(proposal)
    second = authorize_controlled_action(
        proposal,
        existing_authorizations=first["authorizations"],
    )

    assert first["authorization_status"] == "authorized"
    assert second["ok"] is False
    assert second["authorization_status"] == "denied"
    assert second["denial_reason"] == "duplicate_action_authorization"
    assert second["authorization_count"] == 1


def test_2033_lineage_mismatch_rejected(tmp_path: Path) -> None:
    proposal = _proposal(tmp_path)
    proposal["lineage"] = dict(proposal["lineage"])
    proposal["lineage"]["decision_id"] = "wrong-decision"

    result = authorize_controlled_action(proposal)

    assert result["ok"] is False
    assert result["authorization_status"] == "denied"
    assert result["denial_reason"] == "invalid_lineage"


def test_2037_default_does_not_execute(tmp_path: Path, capsys) -> None:
    service = RuntimeOperatorService(_config(tmp_path))
    result = service.run_goal("operator action authorization")
    status = service.status()

    assert result["authorization_status"] == "authorized"
    assert result["authorized"] is False
    assert result["action_authorization"]["authorization_admitted"] is True
    assert result["action_authorization"]["authorized"] is False
    assert result["action_authorization"]["runtime_executed"] is False
    assert result["action_authorization"]["filesystem_mutated"] is False
    assert result["action_authorization"]["code_mutated"] is False
    assert result["action_authorization"]["cursor_advanced"] is False
    assert result["action_authorization"]["progress_memory_written"] is False
    assert status["authorization_status"]["authorization_status"] == "authorized"
    assert status["authorization_status"]["authorized"] is False

    code = zero_runtime_main(
        ["--checkpoint-path", str(tmp_path / "cli-authorization.json"), "run", "task"]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert output["proposal_status"] == "action_proposed"
    assert output["authorization_status"] == "authorized"
    assert output["authorized"] is False
    assert output["action_authorization"]["runtime_executed"] is False


def test_2041_lineage_preserved(tmp_path: Path) -> None:
    proposal = _proposal(tmp_path, "authorization lineage")
    result = authorize_controlled_action(proposal)
    authorization = result["action_authorization"]

    assert authorization["lineage"] == {
        "goal_id": proposal["goal_id"],
        "work_package_id": proposal["work_package_id"],
        "runtime_session_id": proposal["runtime_session_id"],
        "queue_entry_id": proposal["queue_entry_id"],
        "worker_claim_id": proposal["worker_claim_id"],
        "cycle_binding_id": proposal["cycle_binding_id"],
        "execution_request_id": proposal["execution_request_id"],
        "tick_id": proposal["tick_id"],
        "decision_id": proposal["decision_id"],
        "proposal_id": proposal["proposal_id"],
    }


def test_2048_forbidden_runtime_surface_scan() -> None:
    files = [
        Path("core/runtime/runtime_controlled_action_authorization.py"),
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
