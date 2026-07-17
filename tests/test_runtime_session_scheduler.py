from __future__ import annotations

import copy

import pytest

from core.runtime.runtime_operator_session import save_runtime_session, seal_session
from core.runtime.runtime_session_queue import create_scheduler_state, enqueue_session
from core.runtime.runtime_session_scheduler import (compute_scheduler_stats, lease_next_session, recover_scheduler_state,
    release_session_lease)
from tests.test_runtime_session_queue import NOW, session_file

def running_queue(tmp_path):
    path, session, target, workspace = session_file(tmp_path, "running")
    session["session_status"] = "running"; session["required_action"] = "none"; session = seal_session(session); save_runtime_session(session, path)
    state = enqueue_session(create_scheduler_state(state_path=tmp_path / "state.json", now=NOW), path, now=NOW)
    return state, path, session, target, workspace

def test_deterministic_init_waiting_is_not_leased(tmp_path):
    path, session, *_ = session_file(tmp_path, "wait")
    first = create_scheduler_state(state_path=tmp_path / "state.json", now=NOW); second = create_scheduler_state(state_path=tmp_path / "state.json", now=NOW)
    assert first["scheduler_id"] == second["scheduler_id"]
    state = enqueue_session(first, path, now=NOW); state, lease = lease_next_session(state, owner="worker", now=NOW)
    assert lease is None and compute_scheduler_stats(state)["waiting_operator"] == 1

def test_lease_owner_lifetime_exclusivity_and_release(tmp_path):
    state, *_ = running_queue(tmp_path)
    with pytest.raises(ValueError, match="lease_owner_required"): lease_next_session(state, owner="", now=NOW)
    leased, lease = lease_next_session(state, owner="worker", now=NOW); assert lease and lease["mutation_authority"] is False
    again, second = lease_next_session(leased, owner="other", now=NOW); assert second is None
    with pytest.raises(ValueError, match="lease_owner_mismatch"): release_session_lease(leased, lease_id=lease["lease_id"], owner="other", session_id=lease["session_id"], now=NOW)
    released = release_session_lease(leased, lease_id=lease["lease_id"], owner="worker", session_id=lease["session_id"], now=NOW)
    assert released["entries"][0]["lease_status"] == "released"

def test_expired_lease_requeues_and_session_is_source_of_truth(tmp_path):
    state, path, session, *_ = running_queue(tmp_path); leased, _ = lease_next_session(state, owner="worker", now=NOW)
    recovered = recover_scheduler_state(leased, now="2026-07-12T00:01:00+00:00")
    assert recovered["entries"][0]["lease_status"] == "expired"
    session["session_status"] = "failed"; session["failure"] = {"critical": True}; session = seal_session(session); save_runtime_session(session, path)
    recovered = recover_scheduler_state(recovered, now=NOW); assert recovered["entries"][0]["session_status"] == "failed"

