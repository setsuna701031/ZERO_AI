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
from core.runtime.runtime_execution_admission_gate import (
    admit_runtime_execution,
    build_runtime_execution_admission_request,
    evaluate_runtime_execution_admission,
)
from core.runtime.runtime_goal_queue_admission import submit_goal_session_to_queue
from core.runtime.runtime_goal_session_launcher import launch_goal_session
from core.runtime.runtime_operator_service import RuntimeOperatorService
from core.runtime.runtime_queue_worker_pickup import submit_queue_entry_for_worker_pickup


def _config(tmp_path: Path, **overrides):
    data = {
        "runtime_mode": "autonomous",
        "max_tick_limit": 3,
        "checkpoint_path": str(tmp_path / "execution-admission-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _commit(tmp_path: Path, goal: str = "execution admission"):
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
    return commit["action_commit"]


def test_2081_valid_commit_creates_admission(tmp_path: Path) -> None:
    commit = _commit(tmp_path)
    result = admit_runtime_execution(commit)

    assert result["ok"] is True
    assert result["execution_admission_status"] == "admitted"
    assert result["execution_allowed"] is False
    assert result["execution_admission_id"]
    assert result["goal_id"] == commit["goal_id"]
    assert result["session_id"] == commit["runtime_session_id"]
    assert result["queue_id"] == commit["queue_entry_id"]
    assert result["worker_id"] == commit["worker_claim_id"]
    assert result["cycle_id"] == commit["cycle_binding_id"]
    assert result["execution_request_id"] == commit["execution_request_id"]
    assert result["tick_id"] == commit["tick_id"]
    assert result["decision_id"] == commit["decision_id"]
    assert result["proposal_id"] == commit["proposal_id"]
    assert result["authorization_id"] == commit["authorization_id"]
    assert result["commit_id"] == commit["commit_id"]
    assert result["policy_metadata"]["may_prepare_execution"] is True


def test_2085_invalid_commit_rejected(tmp_path: Path) -> None:
    commit = _commit(tmp_path)
    commit["commit_admitted"] = False
    commit["commit_status"] = "rejected"
    commit["denial_reason"] = "blocked_commit"

    result = admit_runtime_execution(commit)

    assert result["ok"] is False
    assert result["execution_admission_status"] == "denied"
    assert result["execution_allowed"] is False
    assert result["denial_reason"] == "blocked_commit"


def test_2089_missing_commit_rejected() -> None:
    request = build_runtime_execution_admission_request(None)
    admission = evaluate_runtime_execution_admission(request)

    assert request["execution_admission_request_created"] is False
    assert request["execution_admission_status"] == "denied"
    assert request["denial_reason"] == "missing_action_commit"
    assert admission["execution_admission_admitted"] is False
    assert admission["execution_admission_status"] == "denied"
    assert admission["denial_reason"] == "missing_action_commit"


def test_2093_duplicate_rejected(tmp_path: Path) -> None:
    commit = _commit(tmp_path)
    first = admit_runtime_execution(commit)
    second = admit_runtime_execution(
        commit,
        existing_admissions=first["admissions"],
    )

    assert first["execution_admission_status"] == "admitted"
    assert second["ok"] is False
    assert second["execution_admission_status"] == "denied"
    assert second["denial_reason"] == "duplicate_execution_admission"
    assert second["admission_count"] == 1


def test_2097_lineage_preserved(tmp_path: Path) -> None:
    commit = _commit(tmp_path, "admission lineage")
    result = admit_runtime_execution(commit)
    admission = result["execution_admission"]

    assert admission["lineage"] == {
        "goal_id": commit["goal_id"],
        "work_package_id": commit["work_package_id"],
        "runtime_session_id": commit["runtime_session_id"],
        "session_id": commit["runtime_session_id"],
        "queue_entry_id": commit["queue_entry_id"],
        "queue_id": commit["queue_entry_id"],
        "worker_claim_id": commit["worker_claim_id"],
        "worker_id": commit["worker_claim_id"],
        "cycle_binding_id": commit["cycle_binding_id"],
        "cycle_id": commit["cycle_binding_id"],
        "execution_request_id": commit["execution_request_id"],
        "tick_id": commit["tick_id"],
        "decision_id": commit["decision_id"],
        "proposal_id": commit["proposal_id"],
        "authorization_id": commit["authorization_id"],
        "commit_id": commit["commit_id"],
    }


def test_2101_lineage_mismatch_rejected(tmp_path: Path) -> None:
    commit = _commit(tmp_path)
    commit["lineage"] = dict(commit["lineage"])
    commit["lineage"]["authorization_id"] = "wrong-authorization"

    result = admit_runtime_execution(commit)

    assert result["ok"] is False
    assert result["execution_admission_status"] == "denied"
    assert result["denial_reason"] == "invalid_lineage"


def test_2105_execution_allowed_remains_false(tmp_path: Path, capsys) -> None:
    service = RuntimeOperatorService(_config(tmp_path))
    result = service.run_goal("operator execution admission")
    status = service.status()

    assert result["execution_admission_status"] == "admitted"
    assert result["execution_allowed"] is False
    assert result["execution_admission"]["execution_admission_admitted"] is True
    assert result["execution_admission"]["execution_allowed"] is False
    assert result["execution_admission"]["runtime_executed"] is False
    assert result["execution_admission"]["filesystem_mutated"] is False
    assert result["execution_admission"]["code_mutated"] is False
    assert result["execution_admission"]["cursor_advanced"] is False
    assert result["execution_admission"]["progress_memory_written"] is False
    assert status["execution_admission_status"]["execution_admission_status"] == "admitted"
    assert status["execution_admission_status"]["execution_allowed"] is False

    code = zero_runtime_main(
        ["--checkpoint-path", str(tmp_path / "cli-admission.json"), "run", "task"]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert output["commit_status"] == "committed"
    assert output["execution_admission_status"] == "admitted"
    assert output["execution_allowed"] is False
    assert output["execution_admission"]["runtime_executed"] is False


def test_2112_forbidden_surface_scan() -> None:
    files = [
        Path("core/runtime/runtime_execution_admission_gate.py"),
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
