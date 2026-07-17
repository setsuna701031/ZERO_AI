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
)
from core.runtime.runtime_controlled_action_commit import (
    build_controlled_action_commit_request,
    commit_controlled_action,
    evaluate_controlled_action_commit_admission,
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
        "checkpoint_path": str(tmp_path / "action-commit-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _authorization(tmp_path: Path, goal: str = "action commit"):
    launch = launch_goal_session(goal, _config(tmp_path))
    queued = submit_goal_session_to_queue(launch)
    pickup = submit_queue_entry_for_worker_pickup(queued["queue_entry"])
    cycle = bind_worker_pickup_to_cycle(pickup["worker_pickup_record"])
    bridge = bridge_cycle_binding_to_execution_request(cycle["cycle_binding"])
    loop = activate_controlled_loop_tick(bridge["execution_request"])
    decision = decide_controlled_tick(loop["controlled_loop_tick"])
    proposal = propose_controlled_action(decision["controlled_tick_decision"])
    authorization = authorize_controlled_action(proposal["action_proposal"])
    return authorization["action_authorization"]


def test_2049_valid_authorization_creates_commit(tmp_path: Path) -> None:
    authorization = _authorization(tmp_path)
    result = commit_controlled_action(authorization)

    assert result["ok"] is True
    assert result["committed"] is True
    assert result["commit_status"] == "committed"
    assert result["commit_id"]
    assert result["goal_id"] == authorization["goal_id"]
    assert result["session_id"] == authorization["runtime_session_id"]
    assert result["queue_id"] == authorization["queue_entry_id"]
    assert result["worker_id"] == authorization["worker_claim_id"]
    assert result["cycle_id"] == authorization["cycle_binding_id"]
    assert result["execution_request_id"] == authorization["execution_request_id"]
    assert result["tick_id"] == authorization["tick_id"]
    assert result["decision_id"] == authorization["decision_id"]
    assert result["proposal_id"] == authorization["proposal_id"]
    assert result["authorization_id"] == authorization["authorization_id"]
    assert result["commit_metadata"]["frozen"] is True
    assert result["commit_metadata"]["commit_means_execute"] is False


def test_2053_denied_authorization_rejected(tmp_path: Path) -> None:
    authorization = _authorization(tmp_path)
    authorization["authorization_admitted"] = False
    authorization["authorization_status"] = "denied"
    authorization["denial_reason"] = "blocked_authorization"

    result = commit_controlled_action(authorization)

    assert result["ok"] is False
    assert result["committed"] is False
    assert result["commit_status"] == "rejected"
    assert result["denial_reason"] == "blocked_authorization"


def test_2057_missing_authorization_rejected() -> None:
    request = build_controlled_action_commit_request(None)
    admission = evaluate_controlled_action_commit_admission(request)

    assert request["commit_request_created"] is False
    assert request["commit_status"] == "rejected"
    assert request["denial_reason"] == "missing_action_authorization"
    assert admission["commit_admitted"] is False
    assert admission["commit_status"] == "rejected"
    assert admission["denial_reason"] == "missing_action_authorization"


def test_2061_duplicate_commit_rejected(tmp_path: Path) -> None:
    authorization = _authorization(tmp_path)
    first = commit_controlled_action(authorization)
    second = commit_controlled_action(
        authorization,
        existing_commits=first["commits"],
    )

    assert first["committed"] is True
    assert second["ok"] is False
    assert second["commit_status"] == "rejected"
    assert second["denial_reason"] == "duplicate_action_commit"
    assert second["commit_count"] == 1


def test_2065_lineage_mismatch_rejected(tmp_path: Path) -> None:
    authorization = _authorization(tmp_path)
    authorization["lineage"] = dict(authorization["lineage"])
    authorization["lineage"]["proposal_id"] = "wrong-proposal"

    result = commit_controlled_action(authorization)

    assert result["ok"] is False
    assert result["commit_status"] == "rejected"
    assert result["denial_reason"] == "invalid_lineage"


def test_2069_commit_preserves_lineage(tmp_path: Path) -> None:
    authorization = _authorization(tmp_path, "commit lineage")
    result = commit_controlled_action(authorization)
    commit = result["action_commit"]

    assert commit["lineage"] == {
        "goal_id": authorization["goal_id"],
        "work_package_id": authorization["work_package_id"],
        "runtime_session_id": authorization["runtime_session_id"],
        "queue_entry_id": authorization["queue_entry_id"],
        "worker_claim_id": authorization["worker_claim_id"],
        "cycle_binding_id": authorization["cycle_binding_id"],
        "execution_request_id": authorization["execution_request_id"],
        "tick_id": authorization["tick_id"],
        "decision_id": authorization["decision_id"],
        "proposal_id": authorization["proposal_id"],
        "authorization_id": authorization["authorization_id"],
    }


def test_2073_commit_does_not_execute(tmp_path: Path, capsys) -> None:
    service = RuntimeOperatorService(_config(tmp_path))
    result = service.run_goal("operator action commit")
    status = service.status()

    assert result["commit_status"] == "committed"
    assert result["committed"] is True
    assert result["action_commit"]["commit_admitted"] is True
    assert result["task_executed"] is False
    assert result["runtime_state_mutated"] is False
    assert result["direct_dispatch_requested"] is False
    assert result["action_commit"]["runtime_executed"] is False
    assert result["action_commit"]["filesystem_mutated"] is False
    assert result["action_commit"]["code_mutated"] is False
    assert result["action_commit"]["cursor_advanced"] is False
    assert result["action_commit"]["progress_memory_written"] is False
    assert status["commit_status"]["commit_status"] == "committed"

    code = zero_runtime_main(
        ["--checkpoint-path", str(tmp_path / "cli-commit.json"), "run", "task"]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert output["authorization_status"] == "authorized"
    assert output["commit_status"] == "committed"
    assert output["action_commit"]["runtime_executed"] is False
    assert output["action_commit"]["commit_metadata"]["commit_means_execute"] is False


def test_2080_forbidden_runtime_surface_scan() -> None:
    files = [
        Path("core/runtime/runtime_controlled_action_commit.py"),
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
