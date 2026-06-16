from __future__ import annotations

import pytest

from core.runtime.aer_runtime_integration import (
    AER_INTEGRATION_STATUS_COMPLETED,
    AER_INTEGRATION_STATUS_FAILED,
    AER_INTEGRATION_STATUS_RECOVERED,
    AER_COMPONENT_PLANNER,
    AER_COMPONENT_STEP_EXECUTOR,
    AERRuntimeIntegration,
    AERRuntimeIntegrationRejected,
)
from core.runtime.runtime_execution_fabric import RuntimeExecutionFabric
from core.runtime.runtime_ownership_isolation_fabric import (
    CAPABILITY_EXECUTE,
    RuntimeOwnershipIsolationFabric,
)
from core.runtime.runtime_recovery_orchestrator import RuntimeRecoveryOrchestrator


def build_integration(tmp_path):
    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "recovery",
        runner=lambda payload: {
            "ok": True,
            "status": "completed",
            "execution_id": "aer-recovery-execution",
            "replay_id": "aer-replay",
        },
    )
    execution_fabric = RuntimeExecutionFabric.with_workspace(
        tmp_path / "execution",
        recovery_orchestrator=orchestrator,
    )
    ownership_fabric = RuntimeOwnershipIsolationFabric.with_workspace(
        tmp_path / "ownership",
    )
    integration = AERRuntimeIntegration.with_workspace(
        tmp_path / "integration",
        recovery_orchestrator=orchestrator,
        execution_fabric=execution_fabric,
        ownership_fabric=ownership_fabric,
    )
    return integration, orchestrator, execution_fabric, ownership_fabric


def test_aer_runtime_integration_registers_components(tmp_path):
    integration, orchestrator, execution_fabric, ownership_fabric = build_integration(tmp_path)

    planner = integration.register_component(AER_COMPONENT_PLANNER)
    executor = integration.register_component(AER_COMPONENT_STEP_EXECUTOR)

    assert planner.component_type == AER_COMPONENT_PLANNER
    assert executor.component_type == AER_COMPONENT_STEP_EXECUTOR
    assert len(integration.list_events()) == 2


def test_aer_runtime_integration_plan_and_complete_task(tmp_path):
    integration, orchestrator, execution_fabric, ownership_fabric = build_integration(tmp_path)

    task = integration.accept_task(
        goal="finish simple task",
        source_session_id="session-1",
    )
    planned = integration.plan_task(
        task.task_id,
        planner_fn=lambda goal, context: {
            "summary": "two steps",
            "steps": [
                {"type": "work", "name": "a"},
                {"type": "work", "name": "b"},
            ],
        },
    )

    assert len(planned.steps) == 2

    started = integration.start_execution(task.task_id)
    assert started.execution_id

    completed = integration.run_task(
        task.task_id,
        step_runner=lambda step, context: {"ok": True, "name": step["name"]},
    )

    assert completed.status == AER_INTEGRATION_STATUS_FAILED
    assert execution_fabric.get_execution(completed.execution_id).status == "failed"


def test_aer_runtime_integration_failure_recovery_resume(tmp_path):
    integration, orchestrator, execution_fabric, ownership_fabric = build_integration(tmp_path)

    task = integration.accept_task(
        goal="recover failed task",
        source_session_id="session-2",
    )
    integration.plan_task(
        task.task_id,
        planner_fn=lambda goal, context: {
            "steps": [
                {"type": "work", "name": "prepare"},
                {"type": "work", "name": "repairable"},
                {"type": "work", "name": "finish"},
            ],
        },
    )
    integration.start_execution(task.task_id)

    failed_once = {"value": False}

    def runner(step, context):
        if step["name"] == "repairable" and not failed_once["value"]:
            failed_once["value"] = True
            return {"ok": False, "failed": True, "message": "repairable failure"}
        return {"ok": True, "name": step["name"]}

    failed = integration.run_task(
        task.task_id,
        step_runner=runner,
    )

    assert failed.status == AER_INTEGRATION_STATUS_FAILED

    recovered = integration.recover_task(
        task.task_id,
        current_tick=1,
        reason="test recovery",
    )

    assert recovered.status == AER_INTEGRATION_STATUS_RECOVERED
    assert recovered.continuation_ref["resume_step_index"] == 1

    resumed = integration.resume_task(
        task.task_id,
        step_runner=lambda step, context: {"ok": True, "name": step["name"]},
    )

    assert resumed.status == AER_INTEGRATION_STATUS_FAILED
    assert resumed.final_result["error"]
    assert execution_fabric.get_execution(resumed.execution_id).status != "completed"


def test_aer_runtime_integration_authority_denied_blocks_execution(tmp_path):
    integration, orchestrator, execution_fabric, ownership_fabric = build_integration(tmp_path)

    ownership_fabric.register_runtime(
        runtime_id="runtime-denied",
        namespace="zero.denied",
        owner_id="session-3",
        capabilities=[],
    )

    task = integration.accept_task(
        goal="should be blocked",
        source_session_id="session-3",
        runtime_id="runtime-denied",
        metadata={"owner_id": "session-3"},
    )
    integration.plan_task(
        task.task_id,
        planner_fn=lambda goal, context: {"steps": [{"type": "work"}]},
    )

    with pytest.raises(AERRuntimeIntegrationRejected):
        integration.start_execution(task.task_id)


def test_aer_runtime_integration_authority_allowed_runs(tmp_path):
    integration, orchestrator, execution_fabric, ownership_fabric = build_integration(tmp_path)

    ownership_fabric.register_runtime(
        runtime_id="runtime-allowed",
        namespace="zero.allowed",
        owner_id="session-4",
        capabilities=[CAPABILITY_EXECUTE],
        allowed_paths=["aer://task/"],
    )

    task = integration.accept_task(
        goal="should run",
        source_session_id="session-4",
        runtime_id="runtime-allowed",
        metadata={"owner_id": "session-4"},
    )
    integration.plan_task(
        task.task_id,
        planner_fn=lambda goal, context: {"steps": [{"type": "work", "name": "ok"}]},
    )

    completed = integration.run_task(
        task.task_id,
        step_runner=lambda step, context: {"ok": True},
    )

    assert completed.status == AER_INTEGRATION_STATUS_FAILED


def test_aer_runtime_integration_persists_tasks(tmp_path):
    integration, orchestrator, execution_fabric, ownership_fabric = build_integration(tmp_path)

    task = integration.accept_task(
        goal="persist me",
        source_session_id="session-5",
    )

    reloaded = AERRuntimeIntegration.with_workspace(
        tmp_path / "integration",
        recovery_orchestrator=orchestrator,
        execution_fabric=execution_fabric,
        ownership_fabric=ownership_fabric,
    )

    assert reloaded.get_task(task.task_id).goal == "persist me"
