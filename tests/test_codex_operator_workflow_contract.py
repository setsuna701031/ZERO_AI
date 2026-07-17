from __future__ import annotations

from core.operator.codex_operator import (

    CodexOperatorState,
    finalize_operator_run,
    get_operator_run,
    list_operator_runs,
    normalize_operator_run,
    run_codex_style_operator,
)
from core.runtime.runtime_transaction_registry import list_transactions
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]



def test_task_intent_repo_scan_plan_apply_verify_summary_flow() -> None:
    result = run_codex_style_operator(task_id="task-op-flow", user_intent="operator workflow", repo_root=_repo(), authority=_authority("task-op-flow"), verification_results=[{"ok": True}])

    assert result.success is False
    assert result.final_state is CodexOperatorState.BLOCKED
    assert result.run.applied_changes == ()
    assert result.run.steps[-2].reason


def test_verification_failure_observe_repair_verify_again_flow() -> None:
    result = run_codex_style_operator(task_id="task-op-repair-flow", user_intent="operator repair workflow", repo_root=_repo(), authority=_authority("task-op-repair-flow"), verification_results=[{"ok": False, "reason": "failed"}])

    assert result.success is False
    assert result.final_state is CodexOperatorState.BLOCKED
    assert result.run.failure_observations == ()
    assert result.run.repair_loop_refs == ()


def test_failed_repair_failed_terminal() -> None:
    result = run_codex_style_operator(task_id="task-op-failed-repair", user_intent="operator failed repair", repo_root=_repo(), authority={}, verification_results=[{"ok": False}], allow_repair=True)

    assert result.success is False
    assert result.final_state in {CodexOperatorState.BLOCKED, CodexOperatorState.FAILED_TERMINAL}


def test_successful_repair_verified_summarized() -> None:
    result = run_codex_style_operator(task_id="task-op-successful-repair", user_intent="operator successful repair", repo_root=_repo(), authority=_authority("task-op-successful-repair"), verification_results=[{"ok": False}])

    assert result.final_state is CodexOperatorState.BLOCKED
    assert result.success is False


def test_selected_files_and_impacted_files_preserved() -> None:
    result = run_codex_style_operator(task_id="task-op-files", user_intent="codex operator", repo_root=_repo(), authority=_authority("task-op-files"), verification_results=[{"ok": True}])

    assert result.run.selected_files
    assert result.run.selected_files == result.run.impacted_files


def test_operator_result_queryable_by_task_id_operator_run_id() -> None:
    result = run_codex_style_operator(task_id="task-op-query", user_intent="operator query", repo_root=_repo(), authority=_authority("task-op-query"), verification_results=[{"ok": True}])

    assert get_operator_run(result.operator_run_id).operator_run_id == result.operator_run_id
    assert result.operator_run_id in [run.operator_run_id for run in list_operator_runs(task_id="task-op-query")]


def test_repeated_same_input_gives_stable_result() -> None:
    first = run_codex_style_operator(task_id="task-op-repeat", user_intent="operator repeat", repo_root=_repo(), authority=_authority("task-op-repeat"), verification_results=[{"ok": True}])
    second = run_codex_style_operator(task_id="task-op-repeat", user_intent="operator repeat", repo_root=_repo(), authority=_authority("task-op-repeat"), verification_results=[{"ok": True}])

    assert normalize_operator_run(first) == normalize_operator_run(second)
    assert first.normalized_digest == second.normalized_digest


def test_no_hidden_mutation_outside_runtime_transaction() -> None:
    before = {tx.transaction_id for tx in list_transactions()}
    result = run_codex_style_operator(task_id="task-op-hidden", user_intent="operator hidden mutation", repo_root=_repo(), authority=_authority("task-op-hidden"), verification_results=[{"ok": True}])
    after = {tx.transaction_id for tx in list_transactions()}

    assert result.run.transaction_refs == ()
    assert after == before


def _authority(task_id: str):
    return {
        "task_id": task_id,
        "step_id": "operator",
        "authority_source": "execution_gateway",
        "runtime_session": f"session-{task_id}",
        "approval_state": "approved",
        "policy_result": {"allowed": True, "decision": "allow"},
        "trace_id": f"trace-{task_id}",
    }


def _repo() -> str:
    return "E:\\zero_ai"
