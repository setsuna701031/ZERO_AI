from __future__ import annotations

import json

import pytest

from core.runtime.runtime_session_queue import create_scheduler_state, enqueue_session, save_scheduler_state
from core.runtime.runtime_worker_service import (create_worker_state, load_worker_state, request_worker_action,
    run_runtime_worker, run_worker_iteration, save_worker_state, worker_health)
from tests.test_runtime_session_queue import NOW, session_file

def setup_worker(tmp_path, *, enqueue=False):
    scheduler_path = tmp_path / "scheduler.json"; worker_path = tmp_path / "worker.json"
    scheduler = create_scheduler_state(state_path=scheduler_path, now=NOW)
    target = tmp_path / "target"; target.mkdir(); workspace = tmp_path / "workspace"; workspace.mkdir()
    if enqueue:
        session_path, session, session_target, session_workspace = session_file(tmp_path, "waiting")
        scheduler = enqueue_session(scheduler, session_path, now=NOW); target, workspace = session_target, session_workspace
    save_scheduler_state(scheduler, scheduler_path)
    worker = create_worker_state(scheduler_state_path=scheduler_path, worker_state_path=worker_path, worker_name="worker-1", target_root=target, now=NOW)
    save_worker_state(worker, worker_path); return scheduler_path, worker_path, worker, target, workspace

def test_deterministic_init_save_load_bom_and_tamper(tmp_path):
    scheduler, path, worker, target, _ = setup_worker(tmp_path)
    second = create_worker_state(scheduler_state_path=scheduler, worker_state_path=path, worker_name="worker-1", target_root=target, now=NOW)
    assert worker["worker_id"] == second["worker_id"] and load_worker_state(path) == worker
    path.write_text("\ufeff" + path.read_text(encoding="utf-8"), encoding="utf-8"); assert load_worker_state(path)["worker_id"] == worker["worker_id"]
    value = json.loads(path.read_text(encoding="utf-8-sig")); value["worker_status"] = "failed"; path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="worker_fingerprint_mismatch"): load_worker_state(path)

def test_idle_iteration_waiting_skipped_heartbeat_and_health(tmp_path):
    scheduler, path, _, target, workspace = setup_worker(tmp_path, enqueue=True)
    result = run_worker_iteration(scheduler_state_path=scheduler, worker_state_path=path, worker_name="worker-1", target_root=target, workspace_root=workspace, now=NOW)
    assert result["worker_status"] == "idle" and result["waiting_dispatches"] == 1 and result["current_lease"] is None
    assert worker_health(result, now=NOW)["healthy"] is True
    assert worker_health(result, now="2026-07-12T00:02:00+00:00")["heartbeat_fresh"] is False

def test_pause_resume_stop_and_bounded_injected_sleep(tmp_path):
    scheduler, path, worker, target, workspace = setup_worker(tmp_path)
    paused = request_worker_action(worker, "pause", now=NOW); save_worker_state(paused, path)
    result = run_worker_iteration(scheduler_state_path=scheduler, worker_state_path=path, worker_name="worker-1", target_root=target, workspace_root=workspace, now=NOW)
    assert result["worker_status"] == "paused" and result["current_lease"] is None
    save_worker_state(request_worker_action(result, "resume", now=NOW), path); sleeps = []
    result = run_runtime_worker(scheduler_state_path=scheduler, worker_state_path=path, worker_name="worker-1", target_root=target, workspace_root=workspace,
        poll_interval_seconds=.1, max_iterations=2, now_provider=lambda: NOW, sleep_provider=sleeps.append)
    assert result["worker_status"] == "stopped" and len(sleeps) == 1

def test_state_path_inside_target_and_invalid_poll_rejected(tmp_path):
    scheduler, _, _, target, workspace = setup_worker(tmp_path)
    with pytest.raises(ValueError, match="inside_target"): create_worker_state(scheduler_state_path=scheduler, worker_state_path=target / "worker.json", worker_name="worker", target_root=target, now=NOW)
    outside = tmp_path / "outside.json"; save_worker_state(create_worker_state(scheduler_state_path=scheduler, worker_state_path=outside, worker_name="worker", target_root=target, now=NOW), outside)
    with pytest.raises(ValueError, match="invalid_poll_interval"): run_runtime_worker(scheduler_state_path=scheduler, worker_state_path=outside, worker_name="worker", target_root=target, workspace_root=workspace, poll_interval_seconds=0)

