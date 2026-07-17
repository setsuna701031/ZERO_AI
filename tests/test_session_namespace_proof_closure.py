from __future__ import annotations

import copy

from core.goals.goal_lineage_contract import canonical_work_identity, extract_goal_lineage
from core.runtime.runtime_failure_recovery_hook import handle_runtime_failure_with_recovery
from core.runtime.runtime_native_multisession_coordination import (
    SIGNAL_TYPE_RECOVERY_REQUEST,
    RuntimeNativeMultiSessionCoordination,
)
from core.runtime.runtime_recovery_execution_contract import RuntimeRecoveryExecutionContractBuilder
from core.runtime.runtime_recovery_orchestrator import RuntimeRecoveryOrchestrator
from core.runtime.runtime_recovery_plan import normalize_runtime_failure
from core.runtime.runtime_replay_engine import build_replayable_workflow_runtime_session
from core.runtime.runtime_supervisor import RuntimeSupervisor
from core.runtime.runtime_watchdog import RuntimeWatchdogIncident
from core.runtime.runtime_watchdog_lease_bridge import RuntimeWatchdogLeaseIncident
from core.runtime.workflow_runtime_session import WorkflowRuntimeSessionManager, build_workflow_runtime_session


def test_01_extract_goal_lineage_compatibility_alias_reaches_work_identity_boundary() -> None:
    lineage = extract_goal_lineage({"root_goal_id": "goal-a", "session_id": "operator-a"})

    assert lineage.get("runtime_session_id", "") == ""
    assert canonical_work_identity(lineage)[2] == ""


def test_02_engineering_goal_loop_default_runtime_identity_is_distinct(tmp_path) -> None:
    from core.tasks.engineering_goal_loop import EngineeringGoalLoop
    from core.tasks.engineering_goal_repository import EngineeringGoalRepository

    captured: dict[str, str] = {}

    class Runner:
        def run_goal(self, goal_id: str, *, goal_lineage=None):
            captured.update(copy.deepcopy(goal_lineage or {}))
            return {"ok": True, "state": "complete", "goal_id": goal_id}

    repository = EngineeringGoalRepository(tmp_path)
    repository.save_goal({"goal_id": "goal-a", "summary": "proof"})
    EngineeringGoalLoop(repo_root=tmp_path, repository=repository, runner=Runner()).run_until_terminal("goal-a", max_cycles=1)

    assert captured["runtime_session_id"] != captured["session_id"]


def test_03_runtime_watchdog_incident_serialization_keeps_namespaces_distinct() -> None:
    payload = RuntimeWatchdogIncident(
        "incident-a",
        "runtime_session_stalled",
        "operator-a",
        runtime_session_id="runtime-a",
        source_session_id="source-a",
    ).to_dict()

    assert payload["session_id"] == "operator-a"
    assert payload["runtime_session_id"] == "runtime-a"
    assert payload["source_session_id"] == "source-a"


def test_04_watchdog_lease_incident_serialization_keeps_namespaces_distinct() -> None:
    payload = RuntimeWatchdogLeaseIncident(
        "incident-a",
        "runtime_session_lease_expired",
        "operator-a",
        runtime_session_id="runtime-a",
        source_session_id="source-a",
    ).to_dict()

    assert payload["session_id"] == "operator-a"
    assert payload["runtime_session_id"] == "runtime-a"
    assert payload["source_session_id"] == "source-a"


def test_05_recovery_orchestrator_does_not_promote_runtime_to_source(tmp_path) -> None:
    ticket = RuntimeRecoveryOrchestrator.with_workspace(tmp_path).submit_incident(
        {"incident_id": "incident-a", "runtime_session_id": "runtime-a", "task_id": "task-a"}
    )

    assert ticket.source_session_id == ""


def test_06_runtime_supervisor_does_not_promote_runtime_to_source(tmp_path) -> None:
    case = RuntimeSupervisor.with_workspace(tmp_path).intake_incident(
        {"incident_id": "incident-a", "runtime_session_id": "runtime-a", "task_id": "task-a"}
    )

    assert case.source_session_id == ""


def test_07_failure_recovery_hook_does_not_promote_operator_to_source() -> None:
    result = handle_runtime_failure_with_recovery(
        task_runtime=object(),
        task={"task_id": "task-a"},
        current_state={"session_id": "operator-a", "runtime_session_id": "runtime-a", "status": "failed"},
        step_result={"ok": False, "error": "proof"},
        auto_recover=False,
    ).to_dict()

    assert result["source_session_id"] == ""
    assert result["failure"]["source_session_id"] == ""


def test_08_recovery_plan_does_not_promote_operator_to_source() -> None:
    failure = normalize_runtime_failure(
        {"session_id": "operator-a", "runtime_session_id": "runtime-a", "status": "failed"}
    )

    assert failure.source_session_id == ""


def test_09_recovery_execution_contract_does_not_promote_operator_to_source() -> None:
    plan = RuntimeRecoveryExecutionContractBuilder()._plan_view_from_source(
        {"recovery_id": "recovery-a", "session_id": "operator-a", "runtime_session_id": "runtime-a", "status": "failed"}
    ).payload["plan"]

    assert plan["source_session_id"] == ""
    assert plan["source_failure"]["source_session_id"] == ""


def test_10_runtime_replay_uses_source_session_only_as_non_runtime_provenance() -> None:
    task = {"task_id": "task-a"}
    source = build_workflow_runtime_session(task=task, state={"task_id": "task-a", "status": "finished"})
    replay = build_replayable_workflow_runtime_session(
        task=task,
        runtime_state={"task_id": "task-a", "workflow_runtime_session": source},
    )

    assert replay["source_session_id"] == source["session_id"]
    assert replay["replay_continuation"]["source_session_id"] == source["session_id"]
    assert "runtime_session_id" not in replay["replay_continuation"]


def test_11_workflow_restore_and_resume_keep_source_as_provenance() -> None:
    manager = WorkflowRuntimeSessionManager()
    source_task = {"task_id": "source-task"}
    source_state = {"task_id": "source-task", "status": "running"}
    checkpoint_session = manager.create_checkpoint(task=source_task, state=source_state)
    checkpoint = checkpoint_session["lineage"]["checkpoints"][-1]

    target_task = {"task_id": "target-task"}
    target_state = {"task_id": "target-task", "status": "running"}
    restored = manager.restore_from_checkpoint(task=target_task, state=target_state, checkpoint=checkpoint)
    restore = restored["lineage"]["restores"][-1]

    assert restore["source_session_id"] == checkpoint["session_id"]
    assert restore["session_id"] == restored["session_id"]
    assert restore["source_session_id"] != restore["session_id"]
    assert "runtime_session_id" not in restore

    resumed = manager.resume_from_recovery_point(
        task=target_task,
        state=target_state,
        recovery_resume_point={
            "recovery_resume_id": "resume-a",
            "workflow_id": checkpoint["workflow_id"],
            "session_id": checkpoint["session_id"],
        },
    )
    recovery_resume = resumed["lineage"]["recovery_resumes"][-1]

    assert recovery_resume["source_session_id"] == checkpoint["session_id"]
    assert recovery_resume["session_id"] == resumed["session_id"]
    assert recovery_resume["source_session_id"] != recovery_resume["session_id"]
    assert "runtime_session_id" not in recovery_resume


def test_12_multisession_missing_source_never_falls_back_to_runtime(tmp_path) -> None:
    captured = []

    class Orchestrator:
        def submit_incident(self, incident, *, current_tick=0):
            captured.append(copy.deepcopy(incident))
            return {"ticket_id": "ticket-a", "incident_id": incident["incident_id"]}

    coordination = RuntimeNativeMultiSessionCoordination.with_workspace(tmp_path, recovery_orchestrator=Orchestrator())
    source = coordination.register_node(runtime_id="runtime-source", namespace="source", owner_id="owner-source")
    target = coordination.register_node(runtime_id="runtime-target", namespace="target", owner_id="owner-target")
    signal = coordination.send_signal(
        source_node_id=source.node_id,
        target_node_id=target.node_id,
        signal_type=SIGNAL_TYPE_RECOVERY_REQUEST,
        payload={"task_id": "task-a"},
    )
    coordination.deliver_signal(signal.signal_id)

    assert captured[0]["source_session_id"] == ""
    assert captured[0]["session_id"] == ""
    assert captured[0]["runtime_session_id"] == "runtime-target"
