from __future__ import annotations

import inspect

from core.operator.codex_operator import (

    CodexOperatorState,
    apply_operator_edit_plan,
    invoke_autonomous_repair,
    run_operator_verification,
    scan_repository_context,
    select_impacted_files,
    start_operator_run,
    create_edit_plan,
)
from core.operator.edit_plan import validate_operator_edit_plan
from core.operator.repo_context_scanner import scan_repo_files
from core.operator import verification_runner
from core.runtime.execution_authority import normalize_authority_metadata, validate_authority_metadata
from core.runtime.runtime_constitution_freeze import assert_prediction_invariant, assert_simulation_invariant
from core.runtime.runtime_transaction_registry import list_transactions
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy, pytest.mark.integration]



def test_operator_context_cannot_grant_authority() -> None:
    normalized = normalize_authority_metadata(context={"operator_context": {"ok": True}}, task={}, step={})
    validation = validate_authority_metadata(normalized, surface="operator_apply_edit")

    assert validation["ok"] is False


def test_edit_plan_cannot_write_files() -> None:
    try:
        validate_operator_edit_plan({"impacted_files": ["a.py"], "target_files": ["a.py"], "test_commands": ["t"], "risk_level": "low", "mutation_executed": True})
    except AssertionError as exc:
        assert "write" in str(exc)
    else:
        raise AssertionError("edit plan file write should fail")


def test_repo_scanner_cannot_run_subprocess() -> None:
    source = inspect.getsource(scan_repo_files)

    assert "subprocess" not in source


def test_verification_runner_cannot_call_subprocess_directly() -> None:
    source = inspect.getsource(verification_runner)

    assert "import subprocess" not in source
    assert "subprocess.run" not in source


def test_operator_apply_edit_requires_runtime_dispatcher_authority() -> None:
    before = {tx.transaction_id for tx in list_transactions()}
    run = apply_operator_edit_plan(_planned("task-op-tx"), authority=_authority("task-op-tx"))
    after = {tx.transaction_id for tx in list_transactions()}

    assert run.final_state is CodexOperatorState.BLOCKED
    assert not run.transaction_refs
    assert after == before
    assert run.steps[-1].reason


def test_failed_verification_invokes_repair_loop_only_when_allowed() -> None:
    run = run_operator_verification(apply_operator_edit_plan(_planned("task-op-repair-allowed"), authority=_authority("task-op-repair-allowed")), authority=_authority("task-op-repair-allowed"), verification_results=[{"ok": False, "reason": "boom"}])
    repaired = invoke_autonomous_repair(run, authority=_authority("task-op-repair-allowed"), allow_repair=True)
    stopped = invoke_autonomous_repair(run, authority=_authority("task-op-repair-allowed"), allow_repair=False)

    assert repaired.repair_loop_refs
    assert stopped.final_state is CodexOperatorState.REQUIRES_HUMAN_REVIEW


def test_requires_human_review_stops_operator_run() -> None:
    run = invoke_autonomous_repair(_planned("task-op-human"), authority=_authority("task-op-human"), allow_repair=False)

    assert run.final_state is CodexOperatorState.REQUIRES_HUMAN_REVIEW


def test_prediction_cannot_approve_operator_edit() -> None:
    try:
        assert_prediction_invariant({"prediction_id": "p", "approval_state": "approved"})
    except AssertionError:
        pass
    else:
        raise AssertionError("prediction approval bypass should fail")


def test_memory_cannot_approve_operator_edit() -> None:
    from core.runtime.runtime_memory_engine import assert_memory_non_authoritative

    try:
        assert_memory_non_authoritative({"memory_id": "m", "kind": "execution_summary", "approval_state": "approved"})
    except AssertionError:
        pass
    else:
        raise AssertionError("memory approval bypass should fail")


def test_operator_preserves_runtime_invariants() -> None:
    run = apply_operator_edit_plan(_planned("task-op-invariants"), authority=_authority("task-op-invariants"))

    assert run.final_state is CodexOperatorState.BLOCKED
    assert_simulation_invariant({"branch_id": "operator-readonly", "parent_trace_id": run.operator_run_id})


def _planned(task_id: str):
    run = start_operator_run(task_id=task_id, user_intent="operator workflow", repo_root=_repo())
    run = scan_repository_context(run)
    run = select_impacted_files(run, ["core/operator/codex_operator.py"])
    return create_edit_plan(run, test_commands=["operator_check"])


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
