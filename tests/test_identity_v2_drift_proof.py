from __future__ import annotations

import copy

from core.adaptive.continuation_runtime import ContinuationRuntime
from core.adaptive.replan_runtime import ReplanRuntime
from core.goals.goal_lineage_contract import GOAL_LINEAGE_FIELDS, attach_goal_lineage, extract_goal_lineage
from core.runtime.persistent_runtime_orchestrator import PersistentRuntimeOrchestrator
from core.runtime.runtime_dispatcher import RuntimeDispatcher
from core.runtime.runtime_execution_fabric import RuntimeExecutionFabric
from core.runtime.runtime_native_multisession_coordination import (
    SIGNAL_TYPE_RECOVERY_REQUEST,
    RuntimeNativeMultiSessionCoordination,
)
from core.runtime.runtime_recovery_continuation import RuntimeRecoveryContinuationLayer
from core.runtime.runtime_recovery_state import (
    RECOVERY_CONTINUATION_READY,
    RECOVERY_EXECUTION_STATUS_COMPLETED,
)
from core.runtime.runtime_session_resume import RuntimeSessionResume
from core.runtime.runtime_transaction_fabric import RuntimeTransactionFabric


def _lineage(*, goal: str = "goal-a") -> dict[str, str]:
    return extract_goal_lineage(
        {
            "root_goal_id": "goal-root",
            "source_goal_id": "goal-source",
            "goal_id": goal,
            "branch_type": "continuation",
            "branch_id": "branch-a",
            "session_id": "session-a",
            "runtime_session_id": "runtime-a",
        },
        require_complete=True,
    )


def _assert_lineage(payload: dict, expected: dict) -> None:
    assert {field: payload.get(field) for field in GOAL_LINEAGE_FIELDS} == {
        field: expected.get(field) for field in GOAL_LINEAGE_FIELDS
    }


def test_canonical_identity_survives_full_cross_runtime_path(tmp_path) -> None:
    canonical = _lineage()
    continuation = ContinuationRuntime.start("goal-a", goal_lineage=canonical).to_dict()
    replan = ReplanRuntime.start(goal_lineage=continuation).to_dict()
    _assert_lineage(continuation, canonical)
    _assert_lineage(replan, canonical)

    class Queue:
        def record_replan_request(self, _package_id, request):
            return {"replan_requests": [copy.deepcopy(request)]}

        def append_replan_steps(self, _package_id, *, request, steps, replan_snapshot):
            return {"last_replan_appended_steps": copy.deepcopy(steps)}

    class Planner:
        def replan_package(self, _record, _request):
            return {"executable_steps": [{"id": "replacement", "type": "work"}]}

    dispatcher = RuntimeDispatcher(
        queue=Queue(),
        task_runner=object(),
        planner_bridge=Planner(),
        workspace_root=tmp_path,
    )
    task = attach_goal_lineage({"task_id": "task-a"}, replan)
    dispatched = dispatcher._replan(
        package_id="package-a",
        record=attach_goal_lineage({"task_id": "task-a", "metadata": {"max_replans": 1}}, replan),
        task=task,
        feedback={"root_cause": "recoverable missing artifact"},
    )
    assert dispatched["ok"] is True
    request = dispatched["replan_request"]
    _assert_lineage(request, canonical)

    execution_fabric = RuntimeExecutionFabric()
    execution = execution_fabric.start_execution(
        source_session_id="source-a",
        task_id="task-a",
        metadata=request,
    )
    execution_incident = execution_fabric.create_recovery_incident(execution.execution_id)
    assert execution_incident["source_session_id"] == "source-a"
    _assert_lineage(execution_incident, canonical)

    transaction_fabric = RuntimeTransactionFabric()
    transaction = transaction_fabric.begin_transaction(
        source_session_id="source-a",
        execution_id=execution.execution_id,
        task_id="task-a",
        metadata=execution_incident,
    )
    transaction_incident = transaction_fabric.create_recovery_incident(transaction.transaction_id)
    assert transaction_incident["source_session_id"] == "source-a"
    _assert_lineage(transaction_incident, canonical)

    handler_states = []

    def handler(_plan, context):
        handler_states.append(copy.deepcopy(context["source_state"]))
        return {"ok": True, "source_state": context["source_state"]}

    source_state = attach_goal_lineage({"status": "failed", "task_id": "task-a"}, transaction_incident)
    recovery = RuntimeRecoveryContinuationLayer(handler=handler)
    plan = recovery.plan_continuation(
        {
            "execution_id": execution.execution_id,
            "recovery_id": "recovery-a",
            "source_session_id": "source-a",
            "status": RECOVERY_EXECUTION_STATUS_COMPLETED,
            "continuation_decision": RECOVERY_CONTINUATION_READY,
            "verification_snapshot": {"verified": True},
            "recovery_chain_status": "verified",
        },
        source_state=source_state,
        approval={"approved": True},
    )
    result = recovery.apply_continuation(plan, approval={"approved": True})

    assert result.applied is True
    assert len(handler_states) == 1
    _assert_lineage(handler_states[0], canonical)


def test_resume_rejects_conflicting_goal_fields_before_scheduler_handoff(tmp_path) -> None:
    class Repository:
        def __init__(self, task):
            self.tasks = [copy.deepcopy(task)]

        def list_tasks(self):
            return copy.deepcopy(self.tasks)

        def save_task(self, task):
            self.tasks = [copy.deepcopy(task)]
            return task

    class Scheduler:
        def __init__(self):
            self.calls = []

        def submit_existing_task(self, task_id, *, goal_lineage):
            self.calls.append((task_id, copy.deepcopy(goal_lineage)))
            return {"ok": True, "task_id": task_id}

    task = attach_goal_lineage({"task_id": "task-a", "status": "running"}, _lineage())
    task["goal_id"] = "goal-drift"
    task["source_goal_id"] = "source-drift"
    store = tmp_path / "resume.json"
    RuntimeSessionResume(workspace_root=tmp_path, storage_path=store).create_session_record(
        session_id="session-a",
        tasks=[task],
    )
    scheduler = Scheduler()

    PersistentRuntimeOrchestrator(
        repo_root=tmp_path,
        workspace_dir=tmp_path / "workspace",
        resume_store_path=store,
        auto_create_resume_record=False,
    ).resume_last_session(
        task_repository=Repository(task),
        scheduler=scheduler,
        session_id="session-a",
    )

    assert scheduler.calls == []


def test_dispatcher_replan_rejects_conflicting_task_lineage_before_planner(tmp_path) -> None:
    class Queue:
        def __init__(self):
            self.request = None

        def record_replan_request(self, package_id, request):
            self.request = copy.deepcopy(request)
            return {"replan_requests": [copy.deepcopy(request)]}

        def append_replan_steps(self, package_id, *, request, steps, replan_snapshot):
            return {"last_replan_appended_steps": copy.deepcopy(steps)}

    class Planner:
        def __init__(self):
            self.calls = []

        def replan_package(self, record, request):
            self.calls.append(copy.deepcopy(request))
            return {"executable_steps": [{"id": "replacement", "type": "work"}]}

    queue = Queue()
    planner = Planner()
    dispatcher = RuntimeDispatcher(
        queue=queue,
        task_runner=object(),
        planner_bridge=planner,
        workspace_root=tmp_path,
    )
    record = attach_goal_lineage({"task_id": "task-a", "metadata": {"max_replans": 1}}, _lineage())
    task = attach_goal_lineage({"task_id": "task-a"}, _lineage())
    task["goal_id"] = "goal-drift"
    task["source_goal_id"] = "source-drift"

    result = dispatcher._replan(
        package_id="package-a",
        record=record,
        task=task,
        feedback={"root_cause": "recoverable missing artifact"},
    )

    assert result["ok"] is False
    assert planner.calls == []


def test_multisession_recovery_keeps_runtime_session_distinct_at_runner(tmp_path) -> None:
    captured = []

    class Orchestrator:
        def submit_incident(self, incident, *, current_tick=0):
            captured.append(copy.deepcopy(incident))
            return {
                "ticket_id": "ticket-a",
                "source_session_id": incident["source_session_id"],
                "incident_id": incident["incident_id"],
                "task_id": incident["task_id"],
            }

    coordination = RuntimeNativeMultiSessionCoordination(
        storage_path=tmp_path / "coordination.json",
        recovery_orchestrator=Orchestrator(),
    )
    source = coordination.register_node(
        runtime_id="runtime-source",
        namespace="source",
        owner_id="owner-source",
        source_session_id="session-source",
        capabilities=["read", "execute"],
    )
    target = coordination.register_node(
        runtime_id="runtime-target",
        namespace="target",
        owner_id="owner-target",
        source_session_id="session-target",
        capabilities=["read", "execute"],
    )

    signal = coordination.send_signal(
        source_node_id=source.node_id,
        target_node_id=target.node_id,
        signal_type=SIGNAL_TYPE_RECOVERY_REQUEST,
        payload={"task_id": "task-a"},
    )
    coordination.deliver_signal(signal.signal_id)

    assert captured[0]["source_session_id"] == "session-target"
    assert captured[0]["runtime_session_id"] == "runtime-target"


def test_recovery_continuation_rejects_conflicting_identity_before_handler() -> None:
    handler_calls = []

    def handler(plan, context):
        handler_calls.append(copy.deepcopy(context["source_state"]))
        return {"ok": True, "source_state": context["source_state"]}

    layer = RuntimeRecoveryContinuationLayer(handler=handler)
    source_state = attach_goal_lineage({"status": "failed", "task_id": "task-a"}, _lineage())
    source_state["root_goal_id"] = "root-drift"
    source_state["runtime_session_id"] = "runtime-drift"
    execution = {
        "execution_id": "execution-a",
        "recovery_id": "recovery-a",
        "source_session_id": "session-a",
        "status": RECOVERY_EXECUTION_STATUS_COMPLETED,
        "continuation_decision": RECOVERY_CONTINUATION_READY,
        "verification_snapshot": {"verified": True},
        "recovery_chain_status": "verified",
    }

    plan = layer.plan_continuation(execution, source_state=source_state, approval={"approved": True})
    result = layer.apply_continuation(plan, approval={"approved": True})

    assert result.applied is False
    assert handler_calls == []
