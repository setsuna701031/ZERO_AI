from __future__ import annotations

from core.tasks.runtime_audit_artifact import build_runtime_audit_artifact
from core.tasks.runtime_audit_registry import RuntimeAuditRegistry
from core.tasks.runtime_replay_snapshot import build_runtime_replay_snapshot


def _artifact(task_id: str, status: str, goal: str = "") -> dict:
    snapshot = build_runtime_replay_snapshot(
        {
            "task_id": task_id,
            "status": status,
            "goal": goal or task_id,
            "runtime_trace": [{"event": "runtime_step_started", "status": status}],
        }
    )
    return build_runtime_audit_artifact(snapshot)


def test_runtime_audit_registry_registers_and_gets_artifact_by_id():
    registry = RuntimeAuditRegistry()
    artifact = _artifact("task-1", "running")

    registered = registry.register_runtime_audit_artifact(artifact)
    loaded = registry.get_runtime_audit_artifact(registered["artifact_id"])

    assert registered["artifact_id"] == artifact["artifact_id"]
    assert loaded == registered
    assert loaded is not registered


def test_runtime_audit_registry_accepts_none_empty_and_malformed_artifacts():
    registry = RuntimeAuditRegistry()

    none_artifact = registry.register_runtime_audit_artifact(None)
    empty_artifact = registry.register_runtime_audit_artifact({})
    malformed_artifact = registry.register_runtime_audit_artifact("bad-artifact")

    assert none_artifact["artifact_id"].startswith("runtime_audit:unknown_task:unknown:")
    assert empty_artifact["artifact_id"].startswith("runtime_audit:unknown_task:unknown:")
    assert malformed_artifact["artifact_id"].startswith("runtime_audit:unknown_task:unknown:")
    assert len(registry.list_runtime_audit_artifacts()) == 3


def test_runtime_audit_registry_lists_with_task_id_and_status_filters():
    registry = RuntimeAuditRegistry()
    first = registry.register_runtime_audit_artifact(_artifact("task-a", "running"))
    second = registry.register_runtime_audit_artifact(_artifact("task-a", "failed"))
    third = registry.register_runtime_audit_artifact(_artifact("task-b", "running"))

    assert [item["artifact_id"] for item in registry.list_runtime_audit_artifacts()] == sorted(
        [first["artifact_id"], second["artifact_id"], third["artifact_id"]]
    )
    assert {item["artifact_id"] for item in registry.list_runtime_audit_artifacts(task_id="task-a")} == {
        first["artifact_id"],
        second["artifact_id"],
    }
    assert {item["artifact_id"] for item in registry.list_runtime_audit_artifacts(status="running")} == {
        first["artifact_id"],
        third["artifact_id"],
    }
    assert registry.list_runtime_audit_artifacts(task_id="task-a", status="running") == [first]


def test_runtime_audit_registry_copies_on_register_and_return():
    registry = RuntimeAuditRegistry()
    artifact = _artifact("task-copy", "running")
    registered = registry.register_runtime_audit_artifact(artifact)

    artifact["status"] = "mutated"
    artifact["timeline"].append({"event": "bad"})

    loaded = registry.get_runtime_audit_artifact(registered["artifact_id"])
    assert loaded["status"] == "running"
    assert len(loaded["timeline"]) == len(registered["timeline"])

    loaded["status"] = "caller-mutated"
    loaded["timeline"].append({"event": "caller-bad"})
    loaded_again = registry.get_runtime_audit_artifact(registered["artifact_id"])

    assert loaded_again["status"] == "running"
    assert len(loaded_again["timeline"]) == len(registered["timeline"])


def test_runtime_audit_registry_clear_removes_state():
    registry = RuntimeAuditRegistry()
    artifact = registry.register_runtime_audit_artifact(_artifact("task-clear", "finished"))

    assert registry.get_runtime_audit_artifact(artifact["artifact_id"]) is not None
    registry.clear()

    assert registry.list_runtime_audit_artifacts() == []
    assert registry.get_runtime_audit_artifact(artifact["artifact_id"]) is None


def test_runtime_audit_registry_uses_existing_artifact_id_when_present():
    registry = RuntimeAuditRegistry()
    artifact = _artifact("task-explicit", "running")
    artifact["artifact_id"] = "explicit-id"

    registered = registry.register_runtime_audit_artifact(artifact)

    assert registered["artifact_id"] == "explicit-id"
    assert registry.get_runtime_audit_artifact("explicit-id") == registered


def test_runtime_audit_registry_fallback_ids_do_not_collide_for_bad_inputs():
    registry = RuntimeAuditRegistry()

    first = registry.register_runtime_audit_artifact({})
    second = registry.register_runtime_audit_artifact({})

    assert first["artifact_id"] != second["artifact_id"]
    assert len(registry.list_runtime_audit_artifacts()) == 2
