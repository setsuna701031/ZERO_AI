from __future__ import annotations

from core.runtime.aer_runtime_integration import AERRuntimeIntegration
from core.runtime.runtime_execution_fabric import RuntimeExecutionFabric
from core.runtime.runtime_native_agent_loop import RuntimeNativeAgentLoop
from core.runtime.runtime_ownership_isolation_fabric import (
    CAPABILITY_EXECUTE,
    RuntimeOwnershipIsolationFabric,
)
from core.runtime.runtime_recovery_orchestrator import RuntimeRecoveryOrchestrator


def build_loop(tmp_path):
    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "recovery",
        runner=lambda payload: {
            "ok": True,
            "status": "completed",
            "execution_id": "loop-recovery-execution",
            "replay_id": "loop-replay",
        },
    )
    execution_fabric = RuntimeExecutionFabric.with_workspace(
        tmp_path / "execution",
        recovery_orchestrator=orchestrator,
    )
    ownership = RuntimeOwnershipIsolationFabric.with_workspace(
        tmp_path / "ownership",
    )
    integration = AERRuntimeIntegration.with_workspace(
        tmp_path / "integration",
        recovery_orchestrator=orchestrator,
        execution_fabric=execution_fabric,
        ownership_fabric=ownership,
    )
    loop = RuntimeNativeAgentLoop.with_workspace(
        tmp_path / "loop",
        aer_integration=integration,
        ownership_fabric=ownership,
    )
    return loop, integration, orchestrator, execution_fabric, ownership


def test_runtime_native_agent_loop_completes_simple_goal(tmp_path):
    loop, integration, orchestrator, execution_fabric, ownership = build_loop(tmp_path)

    record = loop.create_loop(
        source_session_id="session-1",
        owner_id="owner-1",
    )

    completed = loop.run_goal(
        record.loop_id,
        goal="simple goal",
        planner_fn=lambda goal, context: {
            "steps": [
                {"type": "work", "name": "a"},
                {"type": "work", "name": "b"},
            ],
        },
        step_runner=lambda step, context: {"ok": True, "name": step["name"]},
    )

    assert completed.status == "completed"
    assert len(completed.cycles) == 2
    assert completed.task["status"] == "completed"


def test_runtime_native_agent_loop_recovers_and_resumes(tmp_path):
    loop, integration, orchestrator, execution_fabric, ownership = build_loop(tmp_path)

    record = loop.create_loop(
        source_session_id="session-2",
        owner_id="owner-2",
    )

    failed_once = {"value": False}

    def runner(step, context):
        if step["name"] == "repairable" and not failed_once["value"]:
            failed_once["value"] = True
            return {"ok": False, "failed": True, "message": "planned failure"}
        return {"ok": True, "name": step["name"]}

    completed = loop.run_goal(
        record.loop_id,
        goal="recoverable goal",
        planner_fn=lambda goal, context: {
            "steps": [
                {"type": "work", "name": "prepare"},
                {"type": "work", "name": "repairable"},
                {"type": "work", "name": "finish"},
            ],
        },
        step_runner=runner,
        resume_runner=lambda step, context: {"ok": True, "name": step["name"]},
        current_tick=1,
    )

    assert completed.status == "completed"
    assert completed.task["status"] == "completed"
    assert completed.task["continuation_ref"]["resume_step_index"] == 2
    assert len(completed.cycles) == 3
    assert orchestrator.queue.list_tickets()[0].status == "completed"
    assert execution_fabric.get_execution(completed.task["execution_id"]).replay_ref["replay_id"] == "loop-replay"


def test_runtime_native_agent_loop_authority_allowed(tmp_path):
    loop, integration, orchestrator, execution_fabric, ownership = build_loop(tmp_path)

    ownership.register_runtime(
        runtime_id="runtime-allowed",
        namespace="zero.loop",
        owner_id="owner-3",
        capabilities=[CAPABILITY_EXECUTE],
        allowed_paths=["aer://task/"],
    )

    record = loop.create_loop(
        source_session_id="session-3",
        runtime_id="runtime-allowed",
        owner_id="owner-3",
    )

    completed = loop.run_goal(
        record.loop_id,
        goal="authorized goal",
        planner_fn=lambda goal, context: {"steps": [{"type": "work", "name": "x"}]},
        step_runner=lambda step, context: {"ok": True},
    )

    assert completed.status == "completed"


def test_runtime_native_agent_loop_persists(tmp_path):
    loop, integration, orchestrator, execution_fabric, ownership = build_loop(tmp_path)

    record = loop.create_loop(
        source_session_id="session-4",
        owner_id="owner-4",
    )

    reloaded = RuntimeNativeAgentLoop.with_workspace(
        tmp_path / "loop",
        aer_integration=integration,
        ownership_fabric=ownership,
    )

    assert reloaded.get_loop(record.loop_id).loop_id == record.loop_id
