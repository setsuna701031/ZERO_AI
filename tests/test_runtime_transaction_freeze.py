from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_surface_registry import (
    assert_surface_requires_transaction,
    classify_runtime_surface,
)
from core.runtime.runtime_transaction_registry import (
    assert_transaction_lifecycle_valid,
    get_transaction,
    list_transactions,
)


MUTATION_SURFACES = {
    "apply_patch",
    "apply-patch",
    "apply_unified_diff",
    "atomic_edit",
    "write_file",
    "append_file",
    "delete_file",
    "rename_file",
    "patch_transaction",
    "governed_repair_mutation",
    "mutation_apply",
    "mutation_commit",
    "repair_chain_apply",
    "recovery_apply",
    "rollback_restore",
    "git_commit",
    "git_push",
    "git_branch",
    "git_checkout",
    "git_merge",
    "github_write",
    "create_pr",
    "create_issue",
}


def test_mutation_surface_requires_transaction() -> None:
    for surface in MUTATION_SURFACES:
        classified = classify_runtime_surface(surface)
        assert classified.mutation is True, surface
        assert classified.requires_transaction is True, surface
        assert assert_surface_requires_transaction(surface) is True


def test_read_only_surface_does_not_require_transaction() -> None:
    for surface in ("read_file", "list_files", "scan_repo", "replay_read", "review", "policy_check"):
        classified = classify_runtime_surface(surface)
        assert classified.requires_transaction is False, surface


def test_valid_apply_patch_creates_transaction_lifecycle(tmp_path: Path) -> None:
    executor, shared = _executor(tmp_path)
    _write(shared / "tx.txt", "before\n")
    _write(shared / "tx.patch", "--- a/tx.txt\n+++ b/tx.txt\n@@ -1 +1 @@\n-before\n+after\n")

    result = executor.execute_step(
        {
            "type": "apply_patch",
            "patch_path": "workspace/shared/tx.patch",
            "target_path": "workspace/shared/tx.txt",
            "verify_contains": "after",
        },
        task={"confirmed": True},
    )

    runtime_tx = result["runtime_transaction"]
    assert result["ok"] is True
    assert runtime_tx["state"] == "audited"
    assert "verified" in runtime_tx["state_history"]
    assert "committed" in runtime_tx["state_history"]
    assert runtime_tx["affected_files"] == ["workspace/shared/tx.txt"]
    assert assert_transaction_lifecycle_valid(runtime_tx["transaction_id"]) is True


def test_verify_failure_forces_rollback_or_failed_not_committed(tmp_path: Path) -> None:
    executor, shared = _executor(tmp_path)
    _write(shared / "fail.txt", "before\n")
    _write(shared / "fail.patch", "--- a/fail.txt\n+++ b/fail.txt\n@@ -1 +1 @@\n-before\n+after\n")

    result = executor.execute_step(
        {
            "type": "apply_patch",
            "patch_path": "workspace/shared/fail.patch",
            "target_path": "workspace/shared/fail.txt",
            "verify_contains": "missing",
        },
        task={"confirmed": True},
    )

    runtime_tx = result["runtime_transaction"]
    assert result["ok"] is False
    assert "committed" not in runtime_tx["state_history"]
    assert runtime_tx["state"] == "audited"
    assert "failed" in runtime_tx["state_history"]
    assert runtime_tx["failure_result"]
    assert runtime_tx["rollback_result"]


def test_missing_authority_cannot_create_committed_transaction(tmp_path: Path) -> None:
    from core.runtime.step_executor import StepExecutor

    result = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {"type": "write_file", "path": "workspace/shared/noauth.txt", "content": "x"}
    )

    runtime_tx = result["runtime_transaction"]
    assert result["ok"] is False
    assert runtime_tx["state"] == "blocked"
    assert runtime_tx["requires_transaction"] is True
    assert runtime_tx["transaction_id"].startswith("blocked_tx:")


def test_rollback_restore_requires_parent_transaction_or_rollback_evidence() -> None:
    from core.runtime.runtime_transaction_registry import create_transaction

    try:
        create_transaction(
            task_id="task-rollback",
            step_id="step-rollback",
            trace_id="trace-rollback",
            authority_source="execution_gateway",
            surface="rollback_restore",
        )
    except ValueError as exc:
        assert "rollback_restore requires parent transaction" in str(exc)
    else:
        raise AssertionError("rollback_restore without evidence should be rejected")


def test_replay_read_does_not_create_mutation_transaction(tmp_path: Path) -> None:
    from core.runtime.step_executor import StepExecutor

    before = len(list_transactions(trace_id="trace-replay-read"))
    result = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {"type": "read_file", "path": "workspace/shared/missing.txt"},
        context={"trace_id": "trace-replay-read"},
    )

    assert result["ok"] is False
    assert "runtime_transaction" not in result
    assert len(list_transactions(trace_id="trace-replay-read")) == before


def test_recovery_apply_requires_authority_and_transaction(tmp_path: Path) -> None:
    from core.runtime.step_executor import StepExecutor

    denied = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {"type": "recovery_apply", "target_path": "workspace/shared/recovery.txt"}
    )
    assert denied["ok"] is False
    assert denied["runtime_transaction"]["state"] == "blocked"


def test_governed_repair_mutation_creates_transaction(tmp_path: Path) -> None:
    from tests.authority_test_support import owned_step_executor

    result = owned_step_executor(workspace_root=str(tmp_path)).execute_step(
        {"type": "governed_repair_mutation", "target_path": "workspace/shared/repair.txt", "content": "repair"},
        context={"execution_authority": _authority("governed_repair_mutation")},
    )

    assert "runtime_transaction" in result
    assert result["runtime_transaction"]["surface"] == "governed_repair_mutation"
    assert result["runtime_transaction"]["state"] == "audited"


def test_blocked_mutation_leaves_audit_transaction_evidence(tmp_path: Path) -> None:
    from core.runtime.step_executor import StepExecutor

    result = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {"type": "append_file", "path": "workspace/shared/blocked.txt", "content": "x"}
    )

    runtime_tx = result["runtime_transaction"]
    assert result["blocked"] is True
    assert runtime_tx["state"] == "blocked"
    assert runtime_tx["blocked_reason"] == "missing_authority_metadata"


def test_executor_mutation_request_leaves_blocked_transaction_event(tmp_path: Path) -> None:
    from core.runtime.executor import Executor
    from core.runtime.runtime_execution_request import RuntimeExecutionRequest

    result = Executor(workspace_root=tmp_path).execute_request(
        RuntimeExecutionRequest(
            execution_type="mutation_apply",
            command=(),
            metadata={
                **_authority("mutation_apply"),
                "affected_files": ["workspace/shared/executor-mutation.txt"],
            },
            lineage={"request_id": "mutation-request"},
            replay_id="replay:mutation-request",
        )
    )

    runtime_tx = result.metadata["runtime_transaction"]
    assert result.status == "blocked"
    assert runtime_tx["surface"] == "mutation_apply"
    assert runtime_tx["state"] == "blocked"
    assert runtime_tx["blocked_reason"]


def test_no_mutation_reaches_committed_without_verified_success(tmp_path: Path) -> None:
    executor, shared = _executor(tmp_path)
    _write(shared / "bad.py", "def value():\n    return 1\n")
    _write(shared / "bad.patch", "--- a/bad.py\n+++ b/bad.py\n@@ -1,2 +1,2 @@\n def value():\n-    return 1\n+    return (\n")

    result = executor.execute_step(
        {
            "type": "apply_patch",
            "patch_path": "workspace/shared/bad.patch",
            "target_path": "workspace/shared/bad.py",
            "verify_compile": True,
        },
        task={"confirmed": True},
    )

    runtime_tx = get_transaction(result["runtime_transaction"]["transaction_id"])
    assert "committed" not in runtime_tx.state_history
    assert runtime_tx.verification_result.get("ok") is False


def _executor(tmp_path: Path):
    from tests.authority_test_support import owned_step_executor

    workspace = tmp_path / "workspace"
    shared = workspace / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    return owned_step_executor(workspace_root=str(workspace)), shared


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _authority(action_type: str) -> dict:
    return {
        "task_id": f"task-{action_type}",
        "step_id": f"step-{action_type}",
        "authority_source": "execution_gateway",
        "runtime_session": f"session-{action_type}",
        "approval_state": "approved",
        "policy_result": {"allowed": True, "decision": "allow"},
        "trace_id": f"trace-{action_type}",
        "authority_status": "allowed",
        "execution_authority_endpoint": "step_executor",
        "action_type": "mutation",
    }
