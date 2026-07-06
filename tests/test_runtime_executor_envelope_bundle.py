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
from core.runtime.runtime_execution_permit import permit_runtime_execution
from core.runtime.runtime_executor_envelope import (
    build_runtime_executor_envelope_request,
    evaluate_runtime_executor_envelope,
    prepare_runtime_executor_envelope,
)
from core.runtime.runtime_goal_queue_admission import submit_goal_session_to_queue
from core.runtime.runtime_goal_session_launcher import launch_goal_session
from core.runtime.runtime_operator_service import RuntimeOperatorService
from core.runtime.runtime_queue_worker_pickup import submit_queue_entry_for_worker_pickup


def _config(tmp_path: Path, **overrides):
    data = {
        "runtime_mode": "autonomous",
        "max_tick_limit": 3,
        "checkpoint_path": str(tmp_path / "executor-envelope-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _permit(tmp_path: Path, goal: str = "executor envelope"):
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
    permit = permit_runtime_execution(admission["execution_admission"])
    return permit["execution_permit"]


def test_2145_valid_permit_creates_executor_envelope(tmp_path: Path) -> None:
    permit = _permit(tmp_path)
    result = prepare_runtime_executor_envelope(permit)

    assert result["ok"] is True
    assert result["executor_envelope_status"] == "prepared"
    assert result["execution_started"] is False
    assert result["executor_attached"] is False
    assert result["executor_envelope_id"]
    assert result["execution_permit_id"] == permit["execution_permit_id"]
    assert result["execution_admission_id"] == permit["execution_admission_id"]
    assert result["goal_id"] == permit["goal_id"]
    assert result["session_id"] == permit["session_id"]
    assert result["queue_id"] == permit["queue_id"]
    assert result["worker_id"] == permit["worker_id"]
    assert result["cycle_id"] == permit["cycle_id"]
    assert result["execution_request_id"] == permit["execution_request_id"]
    assert result["tick_id"] == permit["tick_id"]
    assert result["decision_id"] == permit["decision_id"]
    assert result["proposal_id"] == permit["proposal_id"]
    assert result["authorization_id"] == permit["authorization_id"]
    assert result["commit_id"] == permit["commit_id"]
    assert result["execution_metadata_snapshot"]["dry_run_container"] is True


def test_2149_denied_permit_rejected(tmp_path: Path) -> None:
    permit = _permit(tmp_path)
    permit["execution_permit_granted"] = False
    permit["permit_status"] = "permit_denied"
    permit["denial_reason"] = "blocked_permit"

    result = prepare_runtime_executor_envelope(permit)

    assert result["ok"] is False
    assert result["executor_envelope_status"] == "rejected"
    assert result["execution_started"] is False
    assert result["executor_attached"] is False
    assert result["denial_reason"] == "blocked_permit"


def test_2153_missing_permit_rejected() -> None:
    request = build_runtime_executor_envelope_request(None)
    envelope = evaluate_runtime_executor_envelope(request)

    assert request["executor_envelope_request_created"] is False
    assert request["executor_envelope_status"] == "rejected"
    assert request["denial_reason"] == "missing_execution_permit"
    assert envelope["executor_envelope_prepared"] is False
    assert envelope["executor_envelope_status"] == "rejected"
    assert envelope["denial_reason"] == "missing_execution_permit"


def test_2157_duplicate_rejected(tmp_path: Path) -> None:
    permit = _permit(tmp_path)
    first = prepare_runtime_executor_envelope(permit)
    second = prepare_runtime_executor_envelope(
        permit,
        existing_envelopes=first["envelopes"],
    )

    assert first["executor_envelope_status"] == "prepared"
    assert second["ok"] is False
    assert second["executor_envelope_status"] == "rejected"
    assert second["denial_reason"] == "duplicate_executor_envelope"
    assert second["envelope_count"] == 1


def test_2161_lineage_preserved(tmp_path: Path) -> None:
    permit = _permit(tmp_path, "envelope lineage")
    result = prepare_runtime_executor_envelope(permit)
    envelope = result["executor_envelope"]

    assert envelope["lineage"] == {
        "goal_id": permit["goal_id"],
        "work_package_id": permit["work_package_id"],
        "runtime_session_id": permit["runtime_session_id"],
        "session_id": permit["session_id"],
        "queue_entry_id": permit["queue_entry_id"],
        "queue_id": permit["queue_id"],
        "worker_claim_id": permit["worker_claim_id"],
        "worker_id": permit["worker_id"],
        "cycle_binding_id": permit["cycle_binding_id"],
        "cycle_id": permit["cycle_id"],
        "execution_request_id": permit["execution_request_id"],
        "tick_id": permit["tick_id"],
        "decision_id": permit["decision_id"],
        "proposal_id": permit["proposal_id"],
        "authorization_id": permit["authorization_id"],
        "commit_id": permit["commit_id"],
        "execution_admission_id": permit["execution_admission_id"],
        "execution_permit_id": permit["execution_permit_id"],
    }


def test_2165_execution_never_starts_or_attaches(tmp_path: Path, capsys) -> None:
    service = RuntimeOperatorService(_config(tmp_path))
    result = service.run_goal("operator executor envelope")
    status = service.status()

    assert result["executor_envelope_status"] == "prepared"
    assert result["execution_started"] is False
    assert result["executor_attached"] is False
    assert result["executor_envelope"]["executor_envelope_prepared"] is True
    assert result["executor_envelope"]["execution_started"] is False
    assert result["executor_envelope"]["executor_attached"] is False
    assert result["executor_envelope"]["runtime_executed"] is False
    assert result["executor_envelope"]["filesystem_mutated"] is False
    assert result["executor_envelope"]["repo_mutated"] is False
    assert result["executor_envelope"]["progress_updated"] is False
    assert result["executor_envelope"]["cursor_moved"] is False
    assert status["executor_envelope_status"]["executor_envelope_status"] == "prepared"
    assert status["executor_envelope_status"]["execution_started"] is False
    assert status["executor_envelope_status"]["executor_attached"] is False

    code = zero_runtime_main(
        ["--checkpoint-path", str(tmp_path / "cli-envelope.json"), "run", "task"]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert output["permit_status"] == "permit_granted"
    assert output["executor_envelope_status"] == "prepared"
    assert output["execution_started"] is False
    assert output["executor_attached"] is False
    assert output["executor_envelope"]["runtime_executed"] is False


def test_2176_forbidden_execution_surface_scan() -> None:
    files = [
        Path("core/runtime/runtime_executor_envelope.py"),
        Path("core/runtime/runtime_operator_service.py"),
        Path("cli/zero_runtime_cli.py"),
    ]
    forbidden = [
        "from core.runtime.executor",
        "import executor",
        "from core.runtime.scheduler",
        "import scheduler",
        "stepexecutor",
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
