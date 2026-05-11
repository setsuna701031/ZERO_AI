from __future__ import annotations

from core.tasks.scheduler import Scheduler


def _gateway_payload(**overrides):
    payload = {
        "contract_version": "planner_contract.v1",
        "action": "noop",
        "raw_action": "noop",
        "goal": "",
        "target_path": None,
        "content": "",
        "command": "",
        "reason": "",
        "metadata": {},
        "is_valid": True,
        "contract_errors": [],
        "contract_warnings": [],
        "adapter_ok": True,
        "adapter_errors": [],
        "adapter_warnings": [],
        "runtime_entry_ok": True,
        "runtime_entry_invoked": True,
        "runtime_entry_error": None,
        "planner_gateway_ok": True,
        "planner_gateway_errors": [],
        "planner_gateway_warnings": [],
        "planner_gateway_error": None,
        "scheduler_planner_gateway_used": True,
        "scheduler_planner_legacy_fallback_used": False,
        "scheduler_planner_runtime_ok": True,
        "scheduler_planner_runtime_error": None,
    }
    payload.update(overrides)
    return payload


def test_scheduler_normalizes_gateway_write_file_payload_to_step():
    scheduler = Scheduler.__new__(Scheduler)

    plan = scheduler._normalize_external_plan(
        _gateway_payload(
            action="write_file",
            raw_action="write",
            goal="write output",
            target_path="workspace/shared/out.txt",
            content="hello",
            metadata={"source": "unit_test"},
        )
    )

    assert plan is not None
    assert plan["planner_mode"] == "planner_contract_gateway"
    assert plan["intent"] == "write_file"
    assert plan["final_answer"] == "write output"

    step = plan["steps"][0]
    assert step["type"] == "write_file"
    assert step["path"] == "workspace/shared/out.txt"
    assert step["target_path"] == "workspace/shared/out.txt"
    assert step["content"] == "hello"
    assert step["planner_contract_action"] == "write_file"
    assert step["metadata"] == {"source": "unit_test"}


def test_scheduler_normalizes_gateway_verify_file_payload_to_verify_step():
    scheduler = Scheduler.__new__(Scheduler)

    plan = scheduler._normalize_external_plan(
        _gateway_payload(
            action="verify_file",
            raw_action="verify",
            goal="verify output",
            target_path="workspace/shared/out.txt",
            reason="post-write check",
        )
    )

    assert plan is not None
    assert plan["intent"] == "verify_file"

    step = plan["steps"][0]
    assert step["type"] == "verify"
    assert step["path"] == "workspace/shared/out.txt"
    assert step["target_path"] == "workspace/shared/out.txt"
    assert step["reason"] == "post-write check"
    assert step["planner_contract_action"] == "verify_file"


def test_scheduler_normalizes_gateway_run_command_payload_to_command_step():
    scheduler = Scheduler.__new__(Scheduler)

    plan = scheduler._normalize_external_plan(
        _gateway_payload(
            action="run_command",
            raw_action="run",
            goal="check python",
            command="python --version",
        )
    )

    assert plan is not None
    assert plan["intent"] == "run_command"

    step = plan["steps"][0]
    assert step["type"] == "command"
    assert step["command"] == "python --version"
    assert step["planner_contract_action"] == "run_command"


def test_scheduler_rejects_invalid_gateway_payload_before_step_creation():
    scheduler = Scheduler.__new__(Scheduler)

    plan = scheduler._normalize_external_plan(
        _gateway_payload(
            action="write_file",
            raw_action="write",
            goal="bad write",
            content="missing target",
            is_valid=False,
            contract_errors=["write_file:missing_target_path"],
            scheduler_planner_runtime_ok=False,
        )
    )

    assert plan is None


def test_scheduler_falls_back_to_legacy_steps_shape():
    scheduler = Scheduler.__new__(Scheduler)

    plan = scheduler._normalize_external_plan(
        {
            "planner_mode": "legacy_test_planner",
            "intent": "task",
            "final_answer": "legacy plan",
            "steps": [
                {
                    "type": "write_file",
                    "path": "workspace/shared/legacy.txt",
                    "content": "legacy",
                }
            ],
        }
    )

    assert plan is not None
    assert plan["planner_mode"] == "legacy_test_planner"
    assert plan["intent"] == "task"
    assert plan["final_answer"] == "legacy plan"
    assert plan["steps"] == [
        {
            "type": "write_file",
            "path": "workspace/shared/legacy.txt",
            "content": "legacy",
        }
    ]