from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager
from core.runtime.runtime_recovery_coordinator import RuntimeRecoveryCoordinator
from core.system.command_dispatch import CommandDispatch


def test_command_dispatch_recovery_lifecycle_commands():
    manager = RuntimeExecutionSessionManager()
    manager.create_session(
        "source-failed-cmd-test",
        "runtime",
        payload={"task_id": "source-failed-cmd-test"},
    )
    manager.start_session("source-failed-cmd-test")
    manager.fail_session(
        "source-failed-cmd-test",
        payload={"error": "manual command recovery probe"},
    )

    coordinator = RuntimeRecoveryCoordinator(session_manager=manager)
    coordinator.create_recovery(
        recovery_id="recovery-cmd-test",
        source_session_id="source-failed-cmd-test",
        payload={"reason": "manual command recovery probe"},
    )

    dispatch = CommandDispatch(recovery_coordinator=coordinator)

    recovery_list = dispatch.dispatch("recovery list")
    assert len(recovery_list) == 1
    assert recovery_list[0].recovery_id == "recovery-cmd-test"

    recovery_status = dispatch.dispatch("recovery status recovery-cmd-test")
    assert recovery_status.recovery_id == "recovery-cmd-test"
    assert recovery_status.status == "created"
    assert recovery_status.verified is False

    recovery_run = dispatch.dispatch("run recovery recovery-cmd-test")
    assert recovery_run.recovery_id == "recovery-cmd-test"
    assert recovery_run.status == "replayed"
    assert recovery_run.verified is False

    recovery_verify = dispatch.dispatch("verify recovery recovery-cmd-test")
    assert recovery_verify.recovery_id == "recovery-cmd-test"
    assert recovery_verify.status == "verified"
    assert recovery_verify.verified is True
