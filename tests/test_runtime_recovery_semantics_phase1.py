from __future__ import annotations

import shutil
from pathlib import Path

from core.runtime.repair_rollback import restore_repair_backup
from core.runtime.runtime_transition_policy import RuntimeTransitionPolicy


REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_ROOT = REPO_ROOT / ".test_tmp" / "runtime_recovery_semantics_phase1"


def setup_function() -> None:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)


def teardown_function() -> None:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)


class RollbackRuntimeProbe:
    def __init__(self, state: dict) -> None:
        self.state = state
        self.called = False

    def load_runtime_state(self, task: dict) -> dict:
        return self.state

    def rollback_last_apply(self, **kwargs):
        self.called = True
        return {
            "ok": True,
            "status": "failed",
            "runtime_state": self.state,
            "rollback_result": {
                "ok": True,
                "reason": "restored",
                "restore_source": "backup",
                "restored_files": ["workspace/shared/demo.py"],
                "failed_files": [],
            },
        }


def test_recovery_policy_blocks_rollback_without_metadata() -> None:
    decision = RuntimeTransitionPolicy().check_recovery_transition(
        current_state={"status": "running", "repair_context": {}},
        updates={"recovery_action": "rollback_restore"},
        owner="task_runtime",
        action="rollback_restore",
    )

    assert decision.ok is False
    assert decision.details["rule"] == "rollback_requires_metadata"


def test_recovery_policy_blocks_rollback_without_restore_available() -> None:
    decision = RuntimeTransitionPolicy().check_recovery_transition(
        current_state={
            "status": "running",
            "repair_context": {
                "rollback": {
                    "restore_available": False,
                }
            },
        },
        updates={"recovery_action": "rollback_restore"},
        owner="task_runtime",
        action="rollback_restore",
    )

    assert decision.ok is False
    assert decision.details["rule"] == "rollback_requires_restore_available"


def test_recovery_policy_allows_rollback_restore_with_metadata() -> None:
    decision = RuntimeTransitionPolicy().check_recovery_transition(
        current_state={
            "status": "running",
            "repair_context": {
                "rollback": {
                    "restore_available": True,
                    "target_path": "workspace/shared/demo.py",
                }
            },
        },
        updates={"recovery_action": "rollback_restore"},
        owner="task_runtime",
        action="rollback_restore",
    )

    assert decision.ok is True
    assert decision.details["rule"] == "recovery_allowed"


def test_recovery_policy_blocks_readonly_rollback_restore() -> None:
    decision = RuntimeTransitionPolicy().check_recovery_transition(
        current_state={
            "status": "running",
            "runtime_mode": "replay",
            "repair_context": {
                "rollback": {
                    "restore_available": True,
                }
            },
        },
        updates={"recovery_action": "rollback_restore"},
        owner="task_runtime",
        action="rollback_restore",
    )

    assert decision.ok is False
    assert decision.details["rule"] == "readonly_runtime_no_rollback_recovery"


def test_recovery_policy_blocks_rollback_reopen_without_successful_result() -> None:
    decision = RuntimeTransitionPolicy().check_recovery_transition(
        current_state={
            "status": "failed",
            "repair_context": {
                "rollback": {
                    "restore_available": True,
                },
                "rollback_result": {
                    "ok": False,
                },
            },
        },
        updates={"status": "retrying", "recovery_action": "rollback_retry"},
        owner="task_runtime",
        action="rollback_retry",
    )

    assert decision.ok is False
    assert decision.details["rule"] == "rollback_reopen_requires_successful_result"


def test_recovery_policy_allows_rollback_reopen_with_successful_result() -> None:
    decision = RuntimeTransitionPolicy().check_recovery_transition(
        current_state={
            "status": "failed",
            "repair_context": {
                "rollback": {
                    "restore_available": True,
                },
                "rollback_result": {
                    "ok": True,
                },
            },
        },
        updates={"status": "retrying", "recovery_action": "rollback_retry"},
        owner="task_runtime",
        action="rollback_retry",
    )

    assert decision.ok is True


def test_restore_repair_backup_blocks_without_rollback_metadata_before_calling_runtime() -> None:
    runtime = RollbackRuntimeProbe({"status": "running", "repair_context": {}})

    result = restore_repair_backup(
        runtime=runtime,
        task={"task_id": "no_rollback_metadata"},
        current_tick=1,
        verify_error="verify failed",
    )

    assert runtime.called is False
    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["rollback_result"]["guard_mode"] == "rollback_recovery_policy_blocked"
    assert result["rollback_result"]["policy_decision"]["details"]["rule"] == "rollback_requires_metadata"


def test_restore_repair_backup_allows_valid_rollback_metadata() -> None:
    runtime = RollbackRuntimeProbe(
        {
            "status": "running",
            "repair_context": {
                "rollback": {
                    "restore_available": True,
                    "target_path": "workspace/shared/demo.py",
                }
            },
        }
    )

    result = restore_repair_backup(
        runtime=runtime,
        task={"task_id": "valid_rollback_metadata"},
        current_tick=1,
        verify_error="verify failed",
    )

    assert runtime.called is True
    assert result["ok"] is True
    assert result["rollback_result"]["ok"] is True
