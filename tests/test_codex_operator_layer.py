from __future__ import annotations

from core.operator.codex_operator import (
    CodexOperatorState,
    apply_operator_edit_plan,
    create_edit_plan,
    finalize_operator_run,
    generate_commit_message,
    normalize_operator_run,
    run_operator_verification,
    scan_repository_context,
    select_impacted_files,
    start_operator_run,
)
from core.operator.edit_plan import validate_operator_edit_plan
from core.operator.repo_context_scanner import build_repo_context_snapshot, normalize_repo_context_snapshot
from core.runtime.runtime_transaction_registry import list_transactions


def test_operator_run_initializes() -> None:
    run = start_operator_run(task_id="task-op-init", user_intent="add operator layer", repo_root=_repo())

    assert run.operator_run_id.startswith("codex_operator_run:")
    assert run.final_state is CodexOperatorState.INITIALIZED


def test_repo_scan_is_read_only() -> None:
    snapshot = build_repo_context_snapshot(_repo(), task_intent="operator")

    assert snapshot.read_only is True
    assert snapshot.authoritative is False
    assert snapshot.mutation_attempted is False


def test_impacted_file_selection_deterministic() -> None:
    first = scan_repository_context(start_operator_run(task_id="task-op-select", user_intent="operator runtime", repo_root=_repo()))
    second = scan_repository_context(start_operator_run(task_id="task-op-select", user_intent="operator runtime", repo_root=_repo()))

    assert first.selected_files == second.selected_files
    assert first.impacted_files == second.impacted_files


def test_edit_plan_is_non_authoritative() -> None:
    run = _planned("task-op-plan")

    assert run.edit_plan["authoritative"] is False
    assert validate_operator_edit_plan(run.edit_plan) is True


def test_operator_apply_edit_requires_authority() -> None:
    run = apply_operator_edit_plan(_planned("task-op-apply-blocked"), authority={})

    assert run.final_state is CodexOperatorState.BLOCKED
    assert not run.transaction_refs


def test_operator_verification_requires_authority() -> None:
    run = run_operator_verification(_planned("task-op-verify-blocked"), authority={})

    assert run.final_state is CodexOperatorState.VERIFICATION_FAILED
    assert run.verification_results[-1]["authority_valid"] is False


def test_operator_run_records_evidence_memory_refs() -> None:
    run = apply_operator_edit_plan(_planned("task-op-refs"), authority=_authority("task-op-refs"))
    run = run_operator_verification(run, authority=_authority("task-op-refs"), verification_results=[{"ok": True}])
    result = finalize_operator_run(run)

    assert result.run.evidence_refs
    assert result.run.memory_refs


def test_operator_result_has_stable_normalized_digest() -> None:
    first = finalize_operator_run(run_operator_verification(apply_operator_edit_plan(_planned("task-op-stable"), authority=_authority("task-op-stable")), authority=_authority("task-op-stable"), verification_results=[{"ok": True}]))
    second = finalize_operator_run(run_operator_verification(apply_operator_edit_plan(_planned("task-op-stable"), authority=_authority("task-op-stable")), authority=_authority("task-op-stable"), verification_results=[{"ok": True}]))

    assert normalize_operator_run(first) == normalize_operator_run(second)
    assert first.normalized_digest == second.normalized_digest


def test_operator_commit_message_generated_from_applied_changes() -> None:
    run = apply_operator_edit_plan(_planned("task-op-message"), authority=_authority("task-op-message"))

    assert "operator" in generate_commit_message(run)


def test_operator_does_not_mutate_without_authority() -> None:
    before = tuple(tx.transaction_id for tx in list_transactions())
    run = apply_operator_edit_plan(_planned("task-op-no-mutate"), authority={})
    after = tuple(tx.transaction_id for tx in list_transactions())

    assert run.final_state is CodexOperatorState.BLOCKED
    assert before == after


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
