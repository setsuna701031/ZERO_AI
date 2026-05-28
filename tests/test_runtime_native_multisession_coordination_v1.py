from __future__ import annotations

from core.runtime.runtime_native_execution_dispatch import RuntimeNativeExecutionDispatch
from core.runtime.runtime_native_mainline import RuntimeNativeMainline
from core.runtime.runtime_native_multisession_coordination import (
    RENDEZVOUS_STATUS_COMPLETED,
    SIGNAL_STATUS_DELIVERED,
    SIGNAL_TYPE_EXECUTION_REQUEST,
    SIGNAL_TYPE_MESSAGE,
    SIGNAL_TYPE_RECOVERY_REQUEST,
    RuntimeNativeMultiSessionCoordination,
)
from core.runtime.runtime_native_scheduler import RuntimeNativeScheduler


def build_coordination(tmp_path):
    mainline = RuntimeNativeMainline.with_workspace(
        tmp_path / "mainline",
        config={
            "runtime_id": "coord-main-runtime",
            "namespace": "zero.coord.main",
            "owner_id": "coord-owner",
            "source_session_id": "coord-session",
            "allowed_paths": ["aer://task/", "workspace/", "runtime-signal://"],
        },
    )
    scheduler = RuntimeNativeScheduler.with_workspace(
        tmp_path / "scheduler",
        mainline=mainline,
    )
    dispatch = RuntimeNativeExecutionDispatch.with_workspace(
        tmp_path / "dispatch",
        mainline=mainline,
        scheduler=scheduler,
    )
    coord = RuntimeNativeMultiSessionCoordination.with_workspace(
        tmp_path / "coordination",
        mainline=mainline,
        scheduler=scheduler,
        dispatch=dispatch,
    )
    return coord, dispatch, scheduler, mainline


def test_multisession_registers_nodes_and_signal_delivery(tmp_path):
    coord, dispatch, scheduler, mainline = build_coordination(tmp_path)

    a = coord.register_node(
        runtime_id="runtime-a",
        namespace="zero.a",
        owner_id="owner-a",
        source_session_id="session-a",
        capabilities=["read", "execute"],
    )
    b = coord.register_node(
        runtime_id="runtime-b",
        namespace="zero.b",
        owner_id="owner-b",
        source_session_id="session-b",
        capabilities=["read", "execute"],
    )

    signal = coord.send_signal(
        source_node_id=a.node_id,
        target_node_id=b.node_id,
        signal_type=SIGNAL_TYPE_MESSAGE,
        payload={"message": "hello"},
    )
    delivered = coord.deliver_signal(signal.signal_id)

    assert delivered.status == SIGNAL_STATUS_DELIVERED
    assert delivered.payload["message"] == "hello"


def test_multisession_rendezvous_completes(tmp_path):
    coord, dispatch, scheduler, mainline = build_coordination(tmp_path)

    a = coord.register_node(runtime_id="runtime-a", namespace="zero.a", owner_id="owner-a")
    b = coord.register_node(runtime_id="runtime-b", namespace="zero.b", owner_id="owner-b")

    rv = coord.open_rendezvous(
        name="test rendezvous",
        required_node_ids=[a.node_id, b.node_id],
    )
    first = coord.join_rendezvous(rv.rendezvous_id, a.node_id)
    second = coord.join_rendezvous(rv.rendezvous_id, b.node_id)

    assert first.status == "joined"
    assert second.status == RENDEZVOUS_STATUS_COMPLETED


def test_multisession_dispatch_between_nodes(tmp_path):
    coord, dispatch, scheduler, mainline = build_coordination(tmp_path)

    a = coord.register_node(
        runtime_id="runtime-a",
        namespace="zero.a",
        owner_id="owner-a",
        source_session_id="session-a",
    )
    b = coord.register_node(
        runtime_id="coord-main-runtime",
        namespace="zero.b",
        owner_id="coord-owner",
        source_session_id="coord-session",
    )

    result = coord.dispatch_between_nodes(
        source_node_id=a.node_id,
        target_node_id=b.node_id,
        goal="cross node execution",
        planner_fn=lambda goal, context: {"steps": [{"type": "work", "name": "x"}]},
        step_runner=lambda step, context: {"ok": True},
    )

    assert result["ok"] is True
    assert result["signal"]["status"] == SIGNAL_STATUS_DELIVERED
    assert result["dispatch"]["status"] == "completed"


def test_multisession_recovery_signal_propagates_to_orchestrator(tmp_path):
    coord, dispatch, scheduler, mainline = build_coordination(tmp_path)

    a = coord.register_node(runtime_id="runtime-a", namespace="zero.a", owner_id="owner-a", source_session_id="session-a")
    b = coord.register_node(runtime_id="coord-main-runtime", namespace="zero.b", owner_id="coord-owner", source_session_id="coord-session")

    signal = coord.send_signal(
        source_node_id=a.node_id,
        target_node_id=b.node_id,
        signal_type=SIGNAL_TYPE_RECOVERY_REQUEST,
        payload={"task_id": "recovery-task", "current_tick": 1},
    )
    delivered = coord.deliver_signal(signal.signal_id)

    assert delivered.status == SIGNAL_STATUS_DELIVERED
    assert delivered.recovery_ref["recovery_ticket"]["source_session_id"] == "coord-session"
    assert len(mainline.orchestrator.queue.list_tickets()) == 1


def test_multisession_persists_state(tmp_path):
    coord, dispatch, scheduler, mainline = build_coordination(tmp_path)

    node = coord.register_node(runtime_id="runtime-a", namespace="zero.a", owner_id="owner-a")

    reloaded = RuntimeNativeMultiSessionCoordination.with_workspace(
        tmp_path / "coordination",
        mainline=mainline,
        scheduler=scheduler,
        dispatch=dispatch,
    )

    assert reloaded.get_node(node.node_id).node_id == node.node_id
