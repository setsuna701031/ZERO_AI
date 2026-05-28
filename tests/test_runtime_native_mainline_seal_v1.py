from __future__ import annotations

from core.runtime.runtime_native_mainline import RuntimeNativeMainline


def test_runtime_native_mainline_full_migration_seal(tmp_path):
    mainline = RuntimeNativeMainline.with_workspace(
        tmp_path,
        config={
            "runtime_id": "seal-mainline-runtime",
            "namespace": "zero.mainline.seal",
            "owner_id": "seal-owner",
            "source_session_id": "seal-session",
            "allowed_paths": ["aer://task/", "workspace/"],
            "denied_paths": ["workspace/system/"],
        },
    )

    failed_once = {"value": False}

    def runner(step, context):
        if step["name"] == "repairable" and not failed_once["value"]:
            failed_once["value"] = True
            return {"ok": False, "failed": True, "message": "planned seal failure"}
        return {"ok": True, "name": step["name"]}

    result = mainline.run_goal(
        "runtime native mainline migration seal",
        planner_fn=lambda goal, context: {
            "summary": "mainline migration seal plan",
            "steps": [
                {"type": "work", "name": "prepare"},
                {"type": "work", "name": "repairable"},
                {"type": "work", "name": "finish"},
            ],
        },
        step_runner=runner,
        resume_runner=lambda step, context: {"ok": True, "name": step["name"]},
        current_tick=2,
    )

    assert result.status == "completed"
    assert result.loop_record["status"] == "completed"
    assert result.loop_record["task"]["status"] == "completed"
    assert result.loop_record["task"]["continuation_ref"]["resume_step_index"] == 2
    assert len(result.loop_record["cycles"]) == 3
    assert len(result.recovery_tickets) == 1
    assert result.recovery_tickets[0]["status"] == "completed"

    health = mainline.health()
    assert health["queue_tickets"] == 1
    assert health["lease_sessions"] == 1
    assert health["watchdog_sessions"] == 1
    assert health["execution_records"] == 1

    lineage = mainline.orchestrator.lineage.lineage_for_ref("seal-session")
    node_types = {node["node_type"] for node in lineage["nodes"]}
    assert "source_session" in node_types
    assert "incident" in node_types
    assert "recovery_ticket" in node_types
    assert "recovery" in node_types
    assert "runtime_replay" in node_types

    denied = mainline.ownership_fabric.authorize(
        runtime_id="seal-mainline-runtime",
        capability="execute",
        target="workspace/system/unsafe.py",
        owner_id="seal-owner",
    )
    assert denied.decision == "deny"

    tick = mainline.supervisor_bridge.tick(current_tick=3).to_dict()
    assert tick["watchdog_lease_result"]["incident_count"] == 0


def test_runtime_native_mainline_seal_persistence_reload(tmp_path):
    mainline = RuntimeNativeMainline.with_workspace(
        tmp_path,
        config={
            "runtime_id": "seal-reload-runtime",
            "namespace": "zero.mainline.reload",
            "owner_id": "reload-owner",
            "source_session_id": "reload-session",
        },
    )

    first = mainline.run_goal(
        "reload seal goal",
        planner_fn=lambda goal, context: {"steps": [{"type": "work", "name": "reload"}]},
        step_runner=lambda step, context: {"ok": True},
    )
    assert first.status == "completed"

    reloaded = RuntimeNativeMainline.with_workspace(tmp_path)
    reloaded.boot()

    latest = reloaded.latest_result()
    assert latest is not None
    assert latest.run_id == first.run_id
    assert reloaded.health()["execution_records"] == 1
    assert reloaded.lease_registry.get_session("reload-session").session_id == "reload-session"
    assert reloaded.watchdog.get_session("reload-session").session_id == "reload-session"
