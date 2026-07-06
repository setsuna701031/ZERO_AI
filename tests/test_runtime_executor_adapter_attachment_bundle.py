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
from core.runtime.runtime_executor_adapter_attachment import (
    attach_runtime_executor_adapter,
    build_runtime_executor_adapter_attachment_request,
    evaluate_runtime_executor_adapter_attachment,
)
from core.runtime.runtime_executor_adapter_binding import bind_runtime_executor_adapter
from core.runtime.runtime_executor_envelope import prepare_runtime_executor_envelope
from core.runtime.runtime_goal_queue_admission import submit_goal_session_to_queue
from core.runtime.runtime_goal_session_launcher import launch_goal_session
from core.runtime.runtime_operator_service import RuntimeOperatorService
from core.runtime.runtime_queue_worker_pickup import submit_queue_entry_for_worker_pickup


def _config(tmp_path: Path, **overrides):
    data = {
        "runtime_mode": "autonomous",
        "max_tick_limit": 3,
        "checkpoint_path": str(tmp_path / "adapter-attachment-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _binding(tmp_path: Path, goal: str = "adapter attachment"):
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
    binding = bind_runtime_executor_adapter(envelope["executor_envelope"])
    return binding["executor_adapter_binding"]


def test_2209_valid_binding_creates_attachment(tmp_path: Path) -> None:
    binding = _binding(tmp_path)
    result = attach_runtime_executor_adapter(binding)

    assert result["ok"] is True
    assert result["adapter_attachment_status"] == "attached"
    assert result["executor_adapter_attached"] is True
    assert result["executor_invoked"] is False
    assert result["execution_started"] is False
    assert result["executor_adapter_attachment_id"]
    assert result["executor_adapter_binding_id"] == binding["adapter_binding_id"]
    assert result["executor_envelope_id"] == binding["executor_envelope_id"]
    assert result["execution_permit_id"] == binding["execution_permit_id"]
    assert result["execution_admission_id"] == binding["execution_admission_id"]
    assert result["goal_id"] == binding["goal_id"]
    assert result["session_id"] == binding["session_id"]
    assert result["queue_id"] == binding["queue_id"]
    assert result["worker_id"] == binding["worker_id"]
    assert result["cycle_id"] == binding["cycle_id"]
    assert result["execution_request_id"] == binding["execution_request_id"]
    assert result["tick_id"] == binding["tick_id"]
    assert result["decision_id"] == binding["decision_id"]
    assert result["proposal_id"] == binding["proposal_id"]
    assert result["authorization_id"] == binding["authorization_id"]
    assert result["commit_id"] == binding["commit_id"]


def test_2213_rejected_binding_rejected(tmp_path: Path) -> None:
    binding = _binding(tmp_path)
    binding["executor_adapter_bound"] = False
    binding["adapter_binding_status"] = "rejected"
    binding["denial_reason"] = "blocked_binding"

    result = attach_runtime_executor_adapter(binding)

    assert result["ok"] is False
    assert result["adapter_attachment_status"] == "rejected"
    assert result["executor_adapter_attached"] is False
    assert result["executor_invoked"] is False
    assert result["execution_started"] is False
    assert result["denial_reason"] == "blocked_binding"


def test_2217_missing_binding_rejected() -> None:
    request = build_runtime_executor_adapter_attachment_request(None)
    attachment = evaluate_runtime_executor_adapter_attachment(request)

    assert request["adapter_attachment_request_created"] is False
    assert request["adapter_attachment_status"] == "rejected"
    assert request["denial_reason"] == "missing_executor_adapter_binding"
    assert attachment["executor_adapter_attached"] is False
    assert attachment["adapter_attachment_status"] == "rejected"
    assert attachment["denial_reason"] == "missing_executor_adapter_binding"


def test_2221_duplicate_rejected(tmp_path: Path) -> None:
    binding = _binding(tmp_path)
    first = attach_runtime_executor_adapter(binding)
    second = attach_runtime_executor_adapter(
        binding,
        existing_attachments=first["attachments"],
    )

    assert first["adapter_attachment_status"] == "attached"
    assert second["ok"] is False
    assert second["adapter_attachment_status"] == "rejected"
    assert second["denial_reason"] == "duplicate_executor_adapter_attachment"
    assert second["attachment_count"] == 1


def test_2225_lineage_preserved(tmp_path: Path) -> None:
    binding = _binding(tmp_path, "adapter attachment lineage")
    result = attach_runtime_executor_adapter(binding)
    attachment = result["executor_adapter_attachment"]

    assert attachment["lineage"] == {
        "goal_id": binding["goal_id"],
        "work_package_id": binding["work_package_id"],
        "runtime_session_id": binding["runtime_session_id"],
        "session_id": binding["session_id"],
        "queue_entry_id": binding["queue_entry_id"],
        "queue_id": binding["queue_id"],
        "worker_claim_id": binding["worker_claim_id"],
        "worker_id": binding["worker_id"],
        "cycle_binding_id": binding["cycle_binding_id"],
        "cycle_id": binding["cycle_id"],
        "execution_request_id": binding["execution_request_id"],
        "tick_id": binding["tick_id"],
        "decision_id": binding["decision_id"],
        "proposal_id": binding["proposal_id"],
        "authorization_id": binding["authorization_id"],
        "commit_id": binding["commit_id"],
        "execution_admission_id": binding["execution_admission_id"],
        "execution_permit_id": binding["execution_permit_id"],
        "executor_envelope_id": binding["executor_envelope_id"],
        "executor_adapter_binding_id": binding["adapter_binding_id"],
    }


def test_2229_attachment_keeps_execution_locked(tmp_path: Path, capsys) -> None:
    service = RuntimeOperatorService(_config(tmp_path))
    result = service.run_goal("operator adapter attachment")
    status = service.status()
    attachment = result["executor_adapter_attachment"]

    assert result["adapter_attachment_status"] == "attached"
    assert result["executor_adapter_attached"] is True
    assert result["executor_invoked"] is False
    assert result["execution_started"] is False
    assert attachment["executor_adapter_attached"] is True
    assert attachment["executor_invoked"] is False
    assert attachment["execution_started"] is False
    assert attachment["adapter_metadata"]["adapter_name"] == "dry_run_executor_adapter"
    assert attachment["capability_snapshot"]["supports_dry_run"] is True
    assert attachment["runtime_executed"] is False
    assert attachment["filesystem_mutated"] is False
    assert attachment["repo_mutated"] is False
    assert attachment["progress_mutated"] is False
    assert attachment["cursor_advanced"] is False
    assert status["adapter_attachment_status"]["adapter_attachment_status"] == "attached"
    assert status["adapter_attachment_status"]["executor_adapter_attached"] is True
    assert status["adapter_attachment_status"]["executor_invoked"] is False
    assert status["adapter_attachment_status"]["execution_started"] is False

    code = zero_runtime_main(
        ["--checkpoint-path", str(tmp_path / "cli-attachment.json"), "run", "task"]
    )
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert output["adapter_binding_status"] == "bound"
    assert output["adapter_attachment_status"] == "attached"
    assert output["executor_adapter_attached"] is True
    assert output["executor_invoked"] is False
    assert output["execution_started"] is False
    assert output["executor_adapter_attachment"]["executor_invoked"] is False


def test_2240_forbidden_execution_surface_scan() -> None:
    files = [
        Path("core/runtime/runtime_executor_adapter_attachment.py"),
        Path("core/runtime/runtime_operator_service.py"),
        Path("cli/zero_runtime_cli.py"),
    ]
    forbidden = [
        "from core.runtime.executor",
        "import executor",
        "stepexecutor",
        "taskrunner",
        "task_runner",
        "subprocess",
        "advance_cursor",
        "progress_memory.write",
        "write_text(",
        "remove_item",
        ".run(",
        "scheduler.advance",
    ]

    for file in files:
        source = file.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in source, f"{token!r} is contained in {file}"
