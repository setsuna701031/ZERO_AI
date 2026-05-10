from __future__ import annotations

from core.tasks.runtime_repair_contract import (
    build_runtime_repair_contract,
    build_runtime_repair_contracts,
    validate_runtime_repair_contract,
)


def test_runtime_repair_contract_for_finished_task_is_observe_only():
    contract = build_runtime_repair_contract(
        {
            "task_id": "task_finished",
            "status": "finished",
            "failed_events": [],
            "blockers": [],
            "latest_event": {"event_type": "runtime_step_completed"},
        }
    )

    assert contract["ok"] is True
    assert contract["suggestion_type"] == "no_repair_needed"
    assert contract["repair_scope"] == "observe_only"
    assert contract["repair_risk"] == "none"
    assert contract["repair_confirmation_required"] is False
    assert contract["repair_budget"]["max_repair_tasks"] == 0
    assert validate_runtime_repair_contract(contract)["ok"] is True


def test_runtime_repair_contract_for_python_failure_is_high_risk_read_only():
    contract = build_runtime_repair_contract(
        {
            "task_id": "task_python_failed",
            "status": "failed",
            "failed_events": [
                {
                    "source": "execution",
                    "event_type": "unknown_event",
                    "action_type": "run_python",
                    "status": "error",
                    "error": {
                        "type": "python_failed",
                        "message": "python failed (code 1)",
                        "classification": "fatal",
                        "max_attempts": 3,
                    },
                }
            ],
        }
    )

    assert contract["suggestion_type"] == "inspect_python_failure"
    assert contract["repair_scope"] == "code_execution_review"
    assert contract["repair_risk"] == "high"
    assert contract["repair_confirmation_required"] is True
    assert "prepare_patch_preview" in contract["repair_allowed_actions"]
    assert "apply_patch" not in contract["repair_allowed_actions"]
    assert contract["repair_budget"]["max_write_actions"] == 0
    assert contract["repair_retry_policy"]["retry_recommended"] is False
    assert "high_risk_failure" in contract["repair_retry_policy"]["blocked_for_types"]


def test_runtime_repair_contract_for_retryable_file_failure_allows_plan_only():
    contract = build_runtime_repair_contract(
        {
            "ok": True,
            "suggestion_type": "inspect_file_operation_failure",
            "severity": "medium",
            "reason": "path missing",
            "recommended_inspection": ["execution_log.json", "runtime_state.json"],
            "retry_recommended": True,
            "human_summary": "file operation failed",
            "task_id": "task_file_failed",
            "status": "failed",
        }
    )

    assert contract["repair_scope"] == "file_operation_review"
    assert contract["repair_risk"] == "medium"
    assert contract["repair_confirmation_required"] is True
    assert "prepare_retry_plan" in contract["repair_allowed_actions"]
    assert "write_file" not in contract["repair_allowed_actions"]
    assert contract["repair_retry_policy"]["retry_recommended"] is True
    assert contract["repair_retry_policy"]["max_attempts"] == 1


def test_runtime_repair_contract_for_blocker_requires_confirmation_without_retry():
    contract = build_runtime_repair_contract(
        {
            "task_id": "task_blocked",
            "status": "blocked",
            "blockers": ["dependency unmet"],
        }
    )

    assert contract["suggestion_type"] == "blocked_task"
    assert contract["repair_scope"] == "blocker_resolution"
    assert contract["repair_risk"] == "medium"
    assert contract["repair_confirmation_required"] is True
    assert contract["repair_retry_policy"]["retry_recommended"] is False
    assert "blocked_task" in contract["repair_retry_policy"]["blocked_for_types"]


def test_runtime_repair_contracts_returns_list_wrapper():
    contracts = build_runtime_repair_contracts({"status": "running", "latest_event": {"event_type": "run_python"}})

    assert len(contracts) == 1
    assert contracts[0]["suggestion_type"] == "observe_running_task"
    assert contracts[0]["repair_risk"] == "low"


def test_validate_runtime_repair_contract_rejects_bad_shapes():
    assert validate_runtime_repair_contract(None)["ok"] is False
    assert validate_runtime_repair_contract({"repair_risk": "weird"})["ok"] is False

    contract = build_runtime_repair_contract({"status": "finished"})
    broken = dict(contract)
    broken["repair_allowed_actions"] = "inspect"
    assert validate_runtime_repair_contract(broken)["ok"] is False
