from __future__ import annotations

import pytest

from core.runtime.runtime_session_lease import (
    LEASE_STATUS_ACTIVE,
    LEASE_STATUS_EXPIRED,
    LEASE_STATUS_RELEASED,
    SESSION_STATUS_ACTIVE,
    SESSION_STATUS_EXPIRED,
    SESSION_STATUS_RELEASED,
    SESSION_STATUS_TRANSFERRED,
    SESSION_STATUS_ZOMBIE,
    RuntimeSessionLeaseRejected,
    RuntimeSessionLeaseRegistry,
)


def test_session_lease_acquire_and_renew(tmp_path):
    registry = RuntimeSessionLeaseRegistry.with_workspace(
        tmp_path,
        default_ttl_ticks=5,
        zombie_after_ticks=20,
    )

    registry.register_session("session-1", task_id="task-1", current_tick=1)
    lease = registry.acquire_lease("session-1", "owner-a", current_tick=1)

    assert lease.status == LEASE_STATUS_ACTIVE
    assert lease.owner_id == "owner-a"
    assert lease.expires_tick == 6

    renewed = registry.renew_lease(lease.lease_id, "owner-a", current_tick=3)
    assert renewed.expires_tick == 8

    session = registry.get_session("session-1")
    assert session.status == SESSION_STATUS_ACTIVE
    assert session.owner_id == "owner-a"


def test_session_lease_rejects_split_brain_owner(tmp_path):
    registry = RuntimeSessionLeaseRegistry.with_workspace(tmp_path)

    registry.register_session("session-2", task_id="task-2", current_tick=1)
    registry.acquire_lease("session-2", "owner-a", current_tick=1)

    with pytest.raises(RuntimeSessionLeaseRejected):
        registry.acquire_lease("session-2", "owner-b", current_tick=2)


def test_session_lease_expiry_allows_new_owner(tmp_path):
    registry = RuntimeSessionLeaseRegistry.with_workspace(
        tmp_path,
        default_ttl_ticks=2,
        zombie_after_ticks=20,
    )

    registry.register_session("session-3", task_id="task-3", current_tick=1)
    old_lease = registry.acquire_lease("session-3", "owner-a", current_tick=1)

    tick = registry.tick(current_tick=4)

    assert tick["expired_sessions"][0]["session_id"] == "session-3"
    assert registry.get_lease(old_lease.lease_id).status == LEASE_STATUS_EXPIRED
    assert registry.get_session("session-3").status == SESSION_STATUS_EXPIRED

    new_lease = registry.acquire_lease("session-3", "owner-b", current_tick=4)
    assert new_lease.owner_id == "owner-b"


def test_session_takeover_transfers_ownership(tmp_path):
    registry = RuntimeSessionLeaseRegistry.with_workspace(tmp_path)

    registry.register_session("session-4", task_id="task-4", current_tick=1)
    registry.acquire_lease("session-4", "owner-a", current_tick=1)

    takeover = registry.takeover_session(
        "session-4",
        "supervisor",
        current_tick=2,
        reason="manual supervisor takeover",
    )

    assert takeover.owner_id == "supervisor"
    assert takeover.previous_owner_id == "owner-a"

    session = registry.get_session("session-4")
    assert session.owner_id == "supervisor"
    assert session.status == SESSION_STATUS_TRANSFERRED
    assert session.takeover_count == 1


def test_session_zombie_detection(tmp_path):
    registry = RuntimeSessionLeaseRegistry.with_workspace(
        tmp_path,
        default_ttl_ticks=20,
        zombie_after_ticks=5,
    )

    registry.register_session("session-5", task_id="task-5", current_tick=1)
    registry.acquire_lease("session-5", "owner-a", current_tick=1)

    result = registry.tick(current_tick=6)

    assert result["zombie_sessions"][0]["session_id"] == "session-5"
    assert registry.get_session("session-5").status == SESSION_STATUS_ZOMBIE


def test_session_zombie_detection_is_independent_from_long_lease(tmp_path):
    registry = RuntimeSessionLeaseRegistry.with_workspace(
        tmp_path,
        default_ttl_ticks=100,
        zombie_after_ticks=5,
    )

    registry.register_session("session-z", task_id="task-z", current_tick=10)
    registry.acquire_lease("session-z", "owner-z", current_tick=10)

    result = registry.tick(current_tick=15)

    assert result["expired_sessions"] == []
    assert result["zombie_sessions"][0]["session_id"] == "session-z"
    assert registry.get_session("session-z").status == SESSION_STATUS_ZOMBIE


def test_release_lease_marks_session_released(tmp_path):
    registry = RuntimeSessionLeaseRegistry.with_workspace(tmp_path)

    registry.register_session("session-6", task_id="task-6", current_tick=1)
    lease = registry.acquire_lease("session-6", "owner-a", current_tick=1)
    released = registry.release_lease(lease.lease_id, "owner-a", current_tick=2)

    assert released.status == LEASE_STATUS_RELEASED
    assert registry.get_session("session-6").status == SESSION_STATUS_RELEASED


def test_session_lease_persists_to_disk(tmp_path):
    registry = RuntimeSessionLeaseRegistry.with_workspace(tmp_path)
    registry.register_session("session-7", task_id="task-7", current_tick=1)
    lease = registry.acquire_lease("session-7", "owner-a", current_tick=1)

    reloaded = RuntimeSessionLeaseRegistry.with_workspace(tmp_path)

    assert reloaded.get_session("session-7").session_id == "session-7"
    assert reloaded.get_lease(lease.lease_id).owner_id == "owner-a"
