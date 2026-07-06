from __future__ import annotations

import json
from pathlib import Path

from cli.zero_runtime_cli import main as zero_runtime_main
from core.runtime.runtime_autonomous_cycle_binding import bind_worker_pickup_to_cycle
from core.runtime.runtime_autonomous_cycle_execution_bridge import (
    bridge_cycle_binding_to_execution_request,
)
from core.runtime.runtime_controlled_action_authorization import authorize_controlled_action
from core.runtime.runtime_controlled_action_commit import commit_controlled_action
from core.runtime.runtime_controlled_action_proposal import propose_controlled_action
from core.runtime.runtime_controlled_loop_activation import activate_controlled_loop_tick
from core.runtime.runtime_controlled_tick_decision import decide_controlled_tick
from core.runtime.runtime_execution_admission_gate import admit_runtime_execution
from core.runtime.runtime_execution_permit import (
    build_runtime_execution_permit_request,
    evaluate_runtime_execution_permit,
    permit_runtime_execution,
)
from core.runtime.runtime_goal_queue_admission import submit_goal_session_to_queue
from core.runtime.runtime_goal_session_launcher import launch_goal_session
from core.runtime.runtime_operator_service import RuntimeOperatorService
from core.runtime.runtime_queue_worker_pickup import submit_queue_entry_for_worker_pickup


def _config(tmp_path: Path, **overrides):
    data = {
        "runtime_mode": "autonomous",
        "max_tick_limit": 3,
        "checkpoint_path": str(tmp_path / "execution-permit-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _admission(tmp_path: Path, goal: str = "execution permit"):
    launch = launch_goal_session(goal, _config(tmp_path))
    queued = submit_goal_session_to_queue(launch)
    pickup = submit_queue_entry_for_worker_pickup(queued["queue_entry"])
    cycle = bind_worker_pickup_to_cycle(pickup["worker_pickup_record"])
    bridge = bridge_cycle_binding_to_execution_request(cycle["cycle_binding"])
    loop = activate_controlled_loop_tick(bridge["execution_request"])
    decision = decide_controlled_tick(loop["controlled_loop_tick"])
    proposal = propose_controlled_action(decision["controlled_tick_decision"])
    authorization = authorize_controlled_action(proposal["action_proposal"])
    commit = commit_controlled_action(authorization["action_authorization"])
    admission = admit_runtime_execution(commit["action_commit"])
    return admission["execution_admission"]


def test_2113_valid_admission_creates_permit_record(tmp_path: Path) -> None:
    admission = _admission(tmp_path)
    result = permit_runtime_execution(admission)

    assert result["ok"] is True
    assert result["permit_status"] == "permit_granted"
    assert result["execution_permitted"] is False
    assert result["execution_permit_id"]
    assert result["execution_admission_id"] == admission["execution_admission_id"]
    assert result["goal_id"] == admission["goal_id"]
    assert result["session_id"] == admission["session_id"]
    assert result["queue_id"] == admission["queue_id"]
    assert result["worker_id"] == admission["worker_id"]
    assert result["cycle_id"] == admission["cycle_id"]
    assert result["execution_request_id"] == admission["execution_request_id"]
    assert result["tick_id"] == admission["tick_id"]
    assert result["decision_id"] == admission["decision_id"]
    assert result["proposal_id"] == admission["proposal_id"]
    assert result["authorization_id"] == admission["authorization_id"]
    assert result["commit_id"] == admission["commit_id"]
    assert result["policy_metadata"]["permit_granted_means_execute"] is False


def test_2118_denied_admission_rejected(tmp_path: Path) -> None:
    admission = _admission(tmp_path)
    admission["execution_admission_admitted"] = False
    admission["execution_admission_status"] = "denied"
    admission["denial_reason"] = "blocked_admission"

    result = permit_runtime_execution(admission)

    assert result["ok"] is False
    assert result["permit_status"] == "permit_denied"
    assert result["execution_permitted"] is False
    assert result["denial_reason"] == "blocked_admission"


def test_2122_missing_admission_rejected() -> None:
    request = build_runtime_execution_permit_request(None)
    permit = evaluate_runtime_execution_permit(request)

    assert request["execution_permit_request_created"] is False
    assert request["permit_status"] == "permit_denied"
    assert request["denial_reason"] == "missing_execution_admission"
    assert permit["execution_permit_granted"] is False
    assert permit["permit_status"] == "permit_denied"
    assert permit["denial_reason"] == "missing_execution_admission"


def test_2126_duplicate_rejected(tmp_path: Path) -> None:
    admission = _admission(tmp_path)
    first = permit_runtime_execution(admission)
    second = permit_runtime_execution(admission, existing_permits=first["permits"])

    assert first["permit_status"] == "permit_granted"
    assert second["ok"] is False
    assert second["permit_status"] == "permit_denied"
    assert second["denial_reason"] == "duplicate_execution_permit"
    assert second["permit_count"] == 1


def test_2130_lineage_preserved(tmp_path: Path) -> None:
    admission = _admission(tmp_path, "permit lineage")
    result = permit_runtime_execution(admission)
    permit = result["execution_permit"]

    assert permit["lineage"] == {
        "goal_id": admission["goal_id"],
        "work_package_id": admission["work_package_id"],
        "runtime_session_id": admission["runtime_session_id"],
        "session_id": admission["session_id"],
        "queue_entry_id": admission["queue_entry_id"],
        "queue_id": admission["queue_id"],
        "worker_claim_id": admission["worker_claim_id"],
        "worker_id": admission["worker_id"],
        "cycle_binding_id": admission["cycle_binding_id"],
        "cycle_id": admission["cycle_id"],
        "execution_request_id": admission["execution_request_id"],
        "tick_id": admission["tick_id"],
        "decision_id": admission["decision_id"],
        "proposal_id": admission["proposal_id"],
        "authorization_id": admission["authorization_id"],
        "commit_id": admission["commit_id"],
        "execution_admission_id": admission["execution_admission_id"],
    }


def test_2134_execution_permitted_remains_false_by_default(
    tmp_path: Path, capsys
) -> None:
    service = RuntimeOperatorService(_config(tmp_path))
    result = service.run_goal("operator execution permit")
    status = service.status()

    assert result["permit_status"] == "permit_granted"
    assert result["execution_permitted"] is False
    assert result["execution_permit"]["execution_permit_granted"] is True
    assert result["execution_permit"]["execution_permitted"] is False
    assert result["execution_permit"]["runtime_executed"] is False
    assert result["execution_permit"]["filesystem_mutated"] is False
    assert result["execution_permit"]["code_mutated"] is False
    assert result["execution_permit"]["repo_mutated"] is False
    assert result["execution_permit"]["cursor_advanced"] is False
    assert result["execution_permit"]["progress_memory_written"] is False
    assert result["execution_permit"]["scheduler_dispatched"] is False
    assert result["execution_permit"]["executor_called"] is False
    assert status["execution_permit_status"]["permit_status"] == "permit_granted"
    assert status["execution_permit_status"]["execution_permitted"] is False

    code = zero_runtime_main(
        ["--checkpoint-path", str(tmp_path / "cli-permit.json"), "run", "task"]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert output["execution_admission_status"] == "admitted"
    assert output["permit_status"] == "permit_granted"
    assert output["execution_permitted"] is False
    assert output["execution_permit"]["runtime_executed"] is False


def test_2144_forbidden_execution_surface_scan() -> None:
    files = [
        Path("core/runtime/runtime_execution_permit.py"),
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
