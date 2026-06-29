from __future__ import annotations

from core.tasks.engineering_runtime_contract import (

    ENGINEERING_RUNTIME_CONTRACT_SCHEMA,
    build_engineering_runtime_contract,
    build_engineering_runtime_contract_from_result,
)
import pytest

pytestmark = [pytest.mark.contract]



def test_build_runtime_contract_is_passive_boundary() -> None:
    contract = build_engineering_runtime_contract(
        goal_id="goal_1",
        action="run_goal",
        ok=True,
        runtime_request={"goals": [{"goal_id": "goal_1"}]},
        runtime_result={"ok": True, "state": "completed"},
        runtime_stdout="done",
        runtime_root_cause={},
        adaptive_decision={"decision": "complete", "reason": "goal_completed"},
        issue_summary={"blocking_issues": []},
    )

    assert contract["schema"] == ENGINEERING_RUNTIME_CONTRACT_SCHEMA
    assert contract["goal_id"] == "goal_1"
    assert contract["runtime_result"]["state"] == "completed"
    assert contract["adaptive_decision"]["decision"] == "complete"
    assert contract["execution_path"]["executes_tasks"] is False
    assert contract["execution_path"]["persists_goal"] is False
    assert contract["execution_path"]["writes_evidence"] is False
    assert contract["execution_path"]["mutates_memory"] is False


def test_normalize_existing_runner_result_without_contract() -> None:
    contract = build_engineering_runtime_contract_from_result(
        {
            "goal_id": "goal_2",
            "action": "run_goal",
            "ok": False,
            "runtime_result": {"ok": False, "state": "replan"},
            "runtime_root_cause": {"stop_reason": "missing_output"},
            "adaptive_decision": {"decision": "replan", "reason": "recoverable_runtime_failure"},
        }
    )

    assert contract["schema"] == ENGINEERING_RUNTIME_CONTRACT_SCHEMA
    assert contract["goal_id"] == "goal_2"
    assert contract["ok"] is False
    assert contract["runtime_root_cause"]["stop_reason"] == "missing_output"
    assert contract["adaptive_decision"]["decision"] == "replan"


def test_normalize_existing_contract_returns_copy() -> None:
    original = build_engineering_runtime_contract(
        goal_id="goal_3",
        action="run_goal",
        ok=True,
        runtime_result={"state": "completed"},
        adaptive_decision={"decision": "complete"},
    )
    wrapped = {"engineering_runtime_contract": original}
    normalized = build_engineering_runtime_contract_from_result(wrapped)

    assert normalized == original
    assert normalized is not original
    normalized["runtime_result"]["state"] = "changed"
    assert original["runtime_result"]["state"] == "completed"
