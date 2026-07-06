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
from core.runtime.runtime_executor_adapter_binding import (
    bind_runtime_executor_adapter,
    build_runtime_executor_adapter_binding_request,
    evaluate_runtime_executor_adapter_binding,
)
from core.runtime.runtime_executor_envelope import prepare_runtime_executor_envelope
from core.runtime.runtime_goal_queue_admission import submit_goal_session_to_queue
from core.runtime.runtime_goal_session_launcher import launch_goal_session
from core.runtime.runtime_operator_service import RuntimeOperatorService
from core.runtime.runtime_queue_worker_pickup import submit_queue_entry_for_worker_pickup


def _config(tmp_path: Path, **overrides):
    data = {
        "runtime_mode": "autonomous",
        "max_tick_limit": 3,
        "checkpoint_path": str(tmp_path / "adapter-binding-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _envelope(tmp_path: Path, goal: str = "adapter binding"):
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
    envelope = prepare_runtime_executor_envelope(permit["execution_permit"])
    return envelope["executor_envelope"]


def test_2177_valid_envelope_creates_adapter_binding(tmp_path: Path) -> None:
    envelope = _envelope(tmp_path)
    result = bind_runtime_executor_adapter(envelope)

    assert result["ok"] is True
    assert result["adapter_binding_status"] == "bound"
    assert result["executor_adapter_bound"] is True
    assert result["executor_invoked"] is False
    assert result["adapter_binding_id"]
    assert result["executor_envelope_id"] == envelope["executor_envelope_id"]
    assert result["execution_permit_id"] == envelope["execution_permit_id"]
    assert result["execution_admission_id"] == envelope["execution_admission_id"]
    assert result["goal_id"] == envelope["goal_id"]
    assert result["session_id"] == envelope["session_id"]
    assert result["queue_id"] == envelope["queue_id"]
    assert result["worker_id"] == envelope["worker_id"]
    assert result["cycle_id"] == envelope["cycle_id"]
    assert result["execution_request_id"] == envelope["execution_request_id"]
    assert result["tick_id"] == envelope["tick_id"]
    assert result["decision_id"] == envelope["decision_id"]
    assert result["proposal_id"] == envelope["proposal_id"]
    assert result["authorization_id"] == envelope["authorization_id"]
    assert result["commit_id"] == envelope["commit_id"]


def test_2181_rejected_envelope_rejected(tmp_path: Path) -> None:
    envelope = _envelope(tmp_path)
    envelope["executor_envelope_prepared"] = False
    envelope["executor_envelope_status"] = "rejected"
    envelope["denial_reason"] = "blocked_envelope"

    result = bind_runtime_executor_adapter(envelope)

    assert result["ok"] is False
    assert result["adapter_binding_status"] == "rejected"
    assert result["executor_adapter_bound"] is False
    assert result["executor_invoked"] is False
    assert result["denial_reason"] == "blocked_envelope"


def test_2185_missing_envelope_rejected() -> None:
    request = build_runtime_executor_adapter_binding_request(None)
    binding = evaluate_runtime_executor_adapter_binding(request)

    assert request["adapter_binding_request_created"] is False
    assert request["adapter_binding_status"] == "rejected"
    assert request["denial_reason"] == "missing_executor_envelope"
    assert binding["executor_adapter_bound"] is False
    assert binding["adapter_binding_status"] == "rejected"
    assert binding["denial_reason"] == "missing_executor_envelope"


def test_2189_duplicate_rejected(tmp_path: Path) -> None:
    envelope = _envelope(tmp_path)
    first = bind_runtime_executor_adapter(envelope)
    second = bind_runtime_executor_adapter(
        envelope,
        existing_bindings=first["bindings"],
    )

    assert first["adapter_binding_status"] == "bound"
    assert second["ok"] is False
    assert second["adapter_binding_status"] == "rejected"
    assert second["denial_reason"] == "duplicate_executor_adapter_binding"
    assert second["binding_count"] == 1


def test_2193_lineage_preserved(tmp_path: Path) -> None:
    envelope = _envelope(tmp_path, "adapter binding lineage")
    result = bind_runtime_executor_adapter(envelope)
    binding = result["executor_adapter_binding"]

    assert binding["lineage"] == {
        "goal_id": envelope["goal_id"],
        "work_package_id": envelope["work_package_id"],
        "runtime_session_id": envelope["runtime_session_id"],
        "session_id": envelope["session_id"],
        "queue_entry_id": envelope["queue_entry_id"],
        "queue_id": envelope["queue_id"],
        "worker_claim_id": envelope["worker_claim_id"],
        "worker_id": envelope["worker_id"],
        "cycle_binding_id": envelope["cycle_binding_id"],
        "cycle_id": envelope["cycle_id"],
        "execution_request_id": envelope["execution_request_id"],
        "tick_id": envelope["tick_id"],
        "decision_id": envelope["decision_id"],
        "proposal_id": envelope["proposal_id"],
        "authorization_id": envelope["authorization_id"],
        "commit_id": envelope["commit_id"],
        "execution_admission_id": envelope["execution_admission_id"],
        "execution_permit_id": envelope["execution_permit_id"],
        "executor_envelope_id": envelope["executor_envelope_id"],
    }


def test_2197_adapter_metadata_exists_and_executor_not_invoked(
    tmp_path: Path, capsys
) -> None:
    service = RuntimeOperatorService(_config(tmp_path))
    result = service.run_goal("operator adapter binding")
    status = service.status()
    binding = result["executor_adapter_binding"]

    assert result["adapter_binding_status"] == "bound"
    assert result["executor_adapter_bound"] is True
    assert result["executor_invoked"] is False
    assert binding["adapter_metadata"]["adapter_name"] == "dry_run_executor_adapter"
    assert binding["adapter_metadata"]["adapter_reference"] == "dry_run_adapter_reference"
    assert binding["adapter_metadata"]["adapter_attached"] is False
    assert binding["adapter_capability_metadata"]["supports_dry_run"] is True
    assert binding["adapter_capability_metadata"]["supports_execution_start"] is False
    assert binding["executor_invoked"] is False
    assert binding["runtime_executed"] is False
    assert binding["filesystem_mutated"] is False
    assert binding["repo_mutated"] is False
    assert binding["progress_mutated"] is False
    assert binding["cursor_advanced"] is False
    assert status["adapter_binding_status"]["adapter_binding_status"] == "bound"
    assert status["adapter_binding_status"]["executor_adapter_bound"] is True
    assert status["adapter_binding_status"]["executor_invoked"] is False

    code = zero_runtime_main(
        ["--checkpoint-path", str(tmp_path / "cli-binding.json"), "run", "task"]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert output["executor_envelope_status"] == "prepared"
    assert output["adapter_binding_status"] == "bound"
    assert output["executor_adapter_bound"] is True
    assert output["executor_invoked"] is False
    assert output["executor_adapter_binding"]["executor_invoked"] is False


def test_2208_forbidden_execution_surface_scan() -> None:
    files = [
        Path("core/runtime/runtime_executor_adapter_binding.py"),
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
