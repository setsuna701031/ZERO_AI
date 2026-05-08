from __future__ import annotations

from core.runtime.execution_session import ExecutionSession
from core.runtime.repair_rollback import restore_repair_backup, should_rollback_after_failed_verify
from core.runtime.repair_step_injector import RepairStepInjector


class RollbackProbeRuntime:
    def __init__(self) -> None:
        self.called = False

    def rollback_last_apply(self, **kwargs):
        self.called = True
        return {
            "ok": True,
            "status": "rolled_back",
            "runtime_state": {},
            "rollback_result": {
                "ok": True,
                "reason": "restored",
                "restore_source": "backup_path",
                "restored_files": ["workspace/shared/example.py"],
                "failed_files": [],
            },
        }


def test_replay_mode_blocks_repair_step_building() -> None:
    result = RepairStepInjector().build_injection(
        repair_plan={
            "ok": True,
            "runtime_mode": "replay",
            "actions": [
                {
                    "type": "write_file",
                    "path": "workspace/shared/example.py",
                    "content": "VALUE = 2\n",
                }
            ],
        },
        task={"task_id": "replay_repair", "runtime_mode": "replay"},
    ).to_dict()

    assert result["ok"] is False
    assert "cannot inject repair steps" in result["reason"]
    assert result["diagnostics"]["guard_mode"] == "readonly_runtime_repair_injection_blocked"


def test_audit_mode_blocks_repair_step_state_injection() -> None:
    try:
        RepairStepInjector().inject_steps_into_state(
            runtime_state={
                "runtime_mode": "audit",
                "steps": [{"type": "verify"}],
                "current_step_index": 0,
            },
            injected_steps=[{"type": "write_file", "path": "workspace/shared/example.py", "content": "x"}],
        )
    except PermissionError as exc:
        assert "audit runtime cannot inject repair steps into state" in str(exc)
    else:
        raise AssertionError("audit runtime should block repair step state injection")


def test_replay_mode_disables_rollback_decision() -> None:
    assert should_rollback_after_failed_verify(
        step={"type": "code_chain_verify"},
        step_result={"ok": False},
        state={
            "runtime_mode": "replay",
            "repair_context": {
                "rollback": {"restore_available": True},
            },
        },
    ) is False


def test_replay_mode_blocks_restore_repair_backup_without_calling_runtime() -> None:
    runtime = RollbackProbeRuntime()

    result = restore_repair_backup(
        runtime=runtime,
        task={"task_id": "replay_rollback", "runtime_mode": "replay"},
        current_tick=1,
        verify_error="verification_failed",
    )

    assert runtime.called is False
    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["runtime_mode"] == "replay"
    assert result["rollback_result"]["guard_mode"] == "readonly_runtime_rollback_blocked"


def test_execution_session_in_readonly_mode_records_observation_not_execution() -> None:
    session = ExecutionSession.start({"task_id": "audit_session", "runtime_mode": "audit"})

    assert session.runtime_mode == "audit"
    assert session.readonly is True
    assert session.status == "observing"

    session.add_step("try_write", "executed", {"path": "workspace/shared/example.py"})
    session.add_tool_result(
        {
            "tool": "write_file",
            "ok": True,
            "side_effect_level": "write",
            "output": {"path": "workspace/shared/example.py"},
        }
    )
    session.finish("finished")

    payload = session.to_dict()
    assert payload["runtime_mode"] == "audit"
    assert payload["readonly"] is True
    assert payload["status"] == "observed"
    assert payload["steps"][0]["status"] == "blocked_readonly"
    assert payload["steps"][0]["detail"]["guard_mode"] == "readonly_runtime_session_step_blocked"
    assert payload["tool_results"][0]["ok"] is False
    assert payload["tool_results"][0]["summary"]["guard_mode"] == "readonly_runtime_session_tool_result_blocked"
