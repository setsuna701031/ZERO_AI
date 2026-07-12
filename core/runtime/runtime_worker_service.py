from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import time
from typing import Any, Callable, Mapping

from core.runtime.runtime_operator_session import fingerprint, load_runtime_session, parse_time, root_identity, time_text
from core.runtime.runtime_session_queue import load_scheduler_state, save_scheduler_state, validate_scheduler_state, WAITING
from core.runtime.runtime_session_scheduler import (LEASE_SECONDS, dispatch_session, lease_next_session,
    recover_scheduler_state, release_session_lease)

CONTRACT = "zero.runtime.worker_service.v1"
HEARTBEAT_FRESH_SECONDS = 90
MIN_POLL_INTERVAL = 0.1
MAX_POLL_INTERVAL = 60.0

def _mapping(value: Any) -> dict[str, Any]: return deepcopy(dict(value)) if isinstance(value, Mapping) else {}
def _unsigned(value: Mapping[str, Any]) -> dict[str, Any]:
    result = _mapping(value); result.pop("worker_fingerprint", None); return result
def seal_worker_state(state: Mapping[str, Any]) -> dict[str, Any]:
    value = _unsigned(state); value["worker_fingerprint"] = fingerprint(value); return value
def validate_worker_state(state: Mapping[str, Any]) -> list[str]:
    value = _mapping(state); reasons = []
    if value.get("contract") != CONTRACT: reasons.append("invalid_worker_contract")
    if value.get("worker_fingerprint") != fingerprint(_unsigned(value)): reasons.append("worker_fingerprint_mismatch")
    if value.get("worker_status") not in {"created", "starting", "running", "idle", "paused", "stopping", "stopped", "blocked", "failed"}: reasons.append("invalid_worker_status")
    if not value.get("worker_id") or not value.get("scheduler_id"): reasons.append("worker_identity_required")
    return reasons

def _unsafe(path: Path) -> bool:
    try: return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except OSError: return False
def _outside_target(path: Path, target_root: Any) -> bool:
    try:
        resolved, target = path.resolve(strict=False), Path(target_root).resolve(strict=True)
        return resolved != target and target not in resolved.parents
    except (OSError, RuntimeError, TypeError): return False

def create_worker_state(*, scheduler_state_path: Any, worker_state_path: Any, worker_name: str,
                        target_root: Any = None, now: Any = None) -> dict[str, Any]:
    if not str(worker_name).strip(): raise ValueError("worker_name_required")
    worker_path = Path(worker_state_path)
    if target_root is not None and not _outside_target(worker_path, target_root): raise ValueError("worker_state_inside_target_root")
    scheduler = load_scheduler_state(scheduler_state_path); at = time_text(now)
    identity = {"worker_name": worker_name.strip(), "scheduler_id": scheduler["scheduler_id"],
        "worker_state_path": str(worker_path.resolve(strict=False)).replace("\\", "/").casefold()}
    return seal_worker_state({"contract": CONTRACT, "worker_id": f"runtime-worker-{fingerprint(identity)[:20]}",
        "worker_name": worker_name.strip(), "worker_status": "created", "scheduler_state_path": str(Path(scheduler_state_path).resolve(strict=True)),
        "scheduler_id": scheduler["scheduler_id"], "worker_state_path": str(worker_path.resolve(strict=False)), "started_at": at,
        "updated_at": at, "last_heartbeat_at": at, "stopped_at": None, "current_lease": None, "current_session_id": None,
        "current_dispatch_id": None, "loop_iteration": 0, "successful_dispatches": 0, "waiting_dispatches": 0,
        "blocked_dispatches": 0, "failed_dispatches": 0, "critical_failures": 0, "recovered_leases": 0,
        "idle_iterations": 0, "last_result": None, "stop_requested": False, "pause_requested": False,
        "failure": None, "audit_record": {"event_type": "runtime_worker_created", "created_at": at}})

def save_worker_state(state: Mapping[str, Any], path: Any) -> dict[str, Any]:
    destination = Path(path)
    if destination.exists() and _unsafe(destination): raise ValueError("unsafe_worker_state_path")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if _unsafe(destination.parent): raise ValueError("unsafe_worker_state_directory")
    value = seal_worker_state(state); temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, destination); return value

def load_worker_state(path: Any) -> dict[str, Any]:
    source = Path(path)
    if _unsafe(source): raise ValueError("unsafe_worker_state_path")
    try: value = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ValueError("invalid_worker_json") from exc
    reasons = validate_worker_state(value)
    if reasons: raise ValueError(";".join(reasons))
    return value

def _heartbeat(state: Mapping[str, Any], status: str, now: Any) -> dict[str, Any]:
    value = _mapping(state); at = time_text(now); value.update(worker_status=status, updated_at=at, last_heartbeat_at=at); return seal_worker_state(value)

def _scheduler_binding(worker: Mapping[str, Any], scheduler: Mapping[str, Any], scheduler_state_path: Any) -> None:
    if worker.get("scheduler_id") != scheduler.get("scheduler_id"): raise ValueError("worker_scheduler_identity_mismatch")
    if str(Path(worker.get("scheduler_state_path", "")).resolve(strict=False)).casefold() != str(Path(scheduler_state_path).resolve(strict=False)).casefold(): raise ValueError("scheduler_state_path_mismatch")

def run_worker_iteration(*, scheduler_state_path: Any, worker_state_path: Any, worker_name: str,
                         target_root: Any, workspace_root: Any, now: Any = None,
                         lease_seconds: int = LEASE_SECONDS, runtime_config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    worker = load_worker_state(worker_state_path); scheduler = load_scheduler_state(scheduler_state_path); _scheduler_binding(worker, scheduler, scheduler_state_path)
    if worker.get("worker_name") != worker_name: raise ValueError("worker_name_mismatch")
    scheduler_before = deepcopy(scheduler); scheduler = recover_scheduler_state(scheduler, now=now)
    recovered = sum(1 for old, new in zip(scheduler_before.get("entries", []), scheduler.get("entries", [])) if old.get("lease_status") == "active" and new.get("lease_status") == "expired")
    worker["recovered_leases"] = int(worker.get("recovered_leases", 0)) + recovered
    worker["loop_iteration"] = int(worker.get("loop_iteration", 0)) + 1
    if worker.get("stop_requested"):
        held = _mapping(worker.get("current_lease"))
        if held:
            try: scheduler = release_session_lease(scheduler, lease_id=held["lease_id"], owner=worker["worker_id"], session_id=held["session_id"], now=now)
            except ValueError: pass
        worker = _heartbeat(worker, "stopping", now); worker["current_lease"] = None; worker["current_session_id"] = None
        worker["worker_status"] = "stopped"; worker["stopped_at"] = time_text(now); save_scheduler_state(scheduler, scheduler_state_path); return save_worker_state(worker, worker_state_path)
    if worker.get("pause_requested"):
        held = _mapping(worker.get("current_lease"))
        if held:
            try: scheduler = release_session_lease(scheduler, lease_id=held["lease_id"], owner=worker["worker_id"], session_id=held["session_id"], now=now)
            except ValueError: pass
            worker["current_lease"] = None; worker["current_session_id"] = None; worker["current_dispatch_id"] = None
        worker["idle_iterations"] = int(worker.get("idle_iterations", 0)) + 1; save_scheduler_state(scheduler, scheduler_state_path); return save_worker_state(_heartbeat(worker, "paused", now), worker_state_path)
    current = _mapping(worker.get("current_lease"))
    if current:
        active = next((item for item in scheduler.get("entries", []) if item.get("session_id") == current.get("session_id") and item.get("lease_id") == current.get("lease_id") and item.get("lease_status") == "active"), None)
        if active is None and parse_time(current.get("expires_at")) <= parse_time(now or datetime.now(timezone.utc)):
            current = {}; worker["current_lease"] = None; worker["current_session_id"] = None; worker["current_dispatch_id"] = None
    if current:
        entry = next((item for item in scheduler.get("entries", []) if item.get("session_id") == current.get("session_id")), None)
        if not entry or entry.get("lease_id") != current.get("lease_id") or entry.get("lease_owner") != worker["worker_id"]:
            worker["failure"] = {"critical": True, "reasons": ["current_lease_identity_mismatch"]}; worker["critical_failures"] += 1
            return save_worker_state(_heartbeat(worker, "failed", now), worker_state_path)
        if entry.get("session_status") in WAITING:
            scheduler = release_session_lease(scheduler, lease_id=current["lease_id"], owner=worker["worker_id"], session_id=current["session_id"], now=now)
            worker["waiting_dispatches"] += 1; worker["current_lease"] = None; worker["current_session_id"] = None
            save_scheduler_state(scheduler, scheduler_state_path); return save_worker_state(_heartbeat(worker, "idle", now), worker_state_path)
    else:
        scheduler, lease = lease_next_session(scheduler, owner=worker["worker_id"], now=now, lifetime_seconds=lease_seconds)
        if lease is None:
            execution_requests = _mapping(_mapping(runtime_config).get("goal_execution_requests"))
            pending_results = _mapping(worker.get("pending_executor_results"))
            for entry in scheduler.get("entries", []):
                session_id = str(entry.get("session_id") or ""); specification = _mapping(execution_requests.get(session_id))
                if not specification or session_id in pending_results or entry.get("session_status") != "waiting_for_candidate_bundle": continue
                try:
                    from core.runtime.runtime_goal_executor import create_goal_execution_request, execute_goal
                    session = load_runtime_session(entry["session_path"], target_root=target_root, workspace_root=workspace_root, now=now)
                    request = create_goal_execution_request(specification.get("goal") or {}, session, operator_context=specification.get("operator_context") or {}, now=now)
                    result = execute_goal(request, workspace_root=target_root, artifact_root=specification.get("artifact_root"), now=now)
                    pending_results[session_id] = result; worker["last_result"] = {"executor_delegated": True, "authoring_engine_delegated": result.get("authoring_output") is not None, "authoring_output_fingerprint": _mapping(result.get("authoring_output")).get("fingerprint"), "session_id": session_id, "execution_status": result.get("execution_status"), "execution_result_fingerprint": result.get("execution_result_fingerprint")}
                except (OSError, TypeError, ValueError) as exc:
                    worker["blocked_dispatches"] += 1; worker["last_result"] = {"executor_delegated": False, "session_id": session_id, "reason": f"{type(exc).__name__}:{exc}"}
            worker["pending_executor_results"] = pending_results
            worker["waiting_dispatches"] += 1 if scheduler.get("waiting_operator_sessions") else 0
            worker["idle_iterations"] = int(worker.get("idle_iterations", 0)) + 1; worker["last_result"] = {"dispatched": False, "reason": "no_dispatchable_session"}
            save_scheduler_state(scheduler, scheduler_state_path); return save_worker_state(_heartbeat(worker, "idle", now), worker_state_path)
        current = lease; worker["current_lease"] = deepcopy(lease); worker["current_session_id"] = lease["session_id"]
        worker["current_dispatch_id"] = f"worker-dispatch-{fingerprint({'worker': worker['worker_id'], 'lease': lease['lease_id']})[:20]}"
        worker = save_worker_state(_heartbeat(worker, "running", now), worker_state_path); save_scheduler_state(scheduler, scheduler_state_path)
    try:
        scheduler, result = dispatch_session(scheduler, owner=worker["worker_id"], target_root=target_root, workspace_root=workspace_root,
            now=now, lease_id=current["lease_id"], dispatch_id=worker["current_dispatch_id"])
        worker["last_result"] = deepcopy(result)
        if result.get("dispatched"):
            worker["successful_dispatches"] += 1
        elif result.get("reason") == "no_dispatchable_session": worker["waiting_dispatches"] += 1
        else: worker["blocked_dispatches"] += 1
    except Exception as exc:
        worker["failed_dispatches"] += 1; worker["failure"] = {"critical": False, "reasons": [f"{type(exc).__name__}:{exc}"]}
        try: scheduler = release_session_lease(scheduler, lease_id=current["lease_id"], owner=worker["worker_id"], session_id=current["session_id"], now=now)
        except ValueError: pass
    worker["current_lease"] = None; worker["current_session_id"] = None; worker["current_dispatch_id"] = None; worker["idle_iterations"] = 0
    save_scheduler_state(scheduler, scheduler_state_path); return save_worker_state(_heartbeat(worker, "running", now), worker_state_path)

def run_runtime_worker(*, scheduler_state_path: Any, worker_state_path: Any, worker_name: str, target_root: Any,
                       workspace_root: Any, poll_interval_seconds: float = 1.0, lease_seconds: int = LEASE_SECONDS,
                       max_iterations: int | None = None, idle_exit_after: int | None = None,
                       now_provider: Callable[[], Any] | None = None, sleep_provider: Callable[[float], None] | None = None,
                       stop_signal: Callable[[], bool] | None = None, runtime_config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    interval = float(poll_interval_seconds)
    if not MIN_POLL_INTERVAL <= interval <= MAX_POLL_INTERVAL: raise ValueError("invalid_poll_interval")
    if max_iterations is not None and (isinstance(max_iterations, bool) or max_iterations < 1): raise ValueError("invalid_max_iterations")
    if idle_exit_after is not None and (isinstance(idle_exit_after, bool) or idle_exit_after < 1): raise ValueError("invalid_idle_exit_after")
    clock, sleeper = now_provider or (lambda: datetime.now(timezone.utc)), sleep_provider or time.sleep
    state = load_worker_state(worker_state_path); state["worker_status"] = "starting"; state["started_at"] = time_text(clock()); state["stopped_at"] = None
    state = save_worker_state(_heartbeat(state, "starting", clock()), worker_state_path); iterations = 0
    while True:
        if stop_signal and stop_signal(): state["stop_requested"] = True; save_worker_state(state, worker_state_path)
        state = run_worker_iteration(scheduler_state_path=scheduler_state_path, worker_state_path=worker_state_path, worker_name=worker_name,
            target_root=target_root, workspace_root=workspace_root, now=clock(), lease_seconds=lease_seconds, runtime_config=runtime_config); iterations += 1
        if state["worker_status"] in {"stopped", "failed"}: break
        if max_iterations is not None and iterations >= max_iterations: state["stop_requested"] = True
        if idle_exit_after is not None and int(state.get("idle_iterations", 0)) >= idle_exit_after: state["stop_requested"] = True
        if state.get("stop_requested"):
            state = save_worker_state(state, worker_state_path)
            state = run_worker_iteration(scheduler_state_path=scheduler_state_path, worker_state_path=worker_state_path, worker_name=worker_name,
                target_root=target_root, workspace_root=workspace_root, now=clock(), lease_seconds=lease_seconds); break
        sleeper(interval)
    return state

def request_worker_action(state: Mapping[str, Any], action: str, *, now: Any = None) -> dict[str, Any]:
    value = _mapping(state)
    if action == "pause": value["pause_requested"] = True; status = "paused"
    elif action == "resume": value["pause_requested"] = False; value["stop_requested"] = False; status = "idle"
    elif action == "stop": value["stop_requested"] = True; status = "stopping"
    else: raise ValueError("invalid_worker_action")
    return _heartbeat(value, status, now)

def worker_health(state: Mapping[str, Any], *, scheduler_state: Mapping[str, Any] | None = None, now: Any = None) -> dict[str, Any]:
    value = _mapping(state); reasons = validate_worker_state(value); current = parse_time(now or datetime.now(timezone.utc))
    try: fresh = (current - parse_time(value.get("last_heartbeat_at"))).total_seconds() <= HEARTBEAT_FRESH_SECONDS
    except (TypeError, ValueError): fresh = False
    if not fresh: reasons.append("stale_heartbeat")
    scheduler_valid = None if scheduler_state is None else not validate_scheduler_state(scheduler_state)
    if scheduler_valid is False: reasons.append("scheduler_state_invalid")
    lease_valid = None if not value.get("current_lease") else parse_time(value["current_lease"].get("expires_at")) > current
    if lease_valid is False: reasons.append("current_lease_expired")
    critical = value.get("worker_status") == "failed" or _mapping(value.get("failure")).get("critical") is True
    if critical: reasons.append("critical_failure")
    return {"healthy": not reasons and value.get("worker_status") not in {"blocked", "failed"}, "worker_status": value.get("worker_status"),
        "heartbeat_fresh": fresh, "scheduler_state_valid": scheduler_valid, "current_lease_valid": lease_valid,
        "last_dispatch_status": _mapping(value.get("last_result")).get("session_status") or _mapping(value.get("last_result")).get("reason"),
        "critical_failure": critical, "reasons": reasons}

__all__ = ["CONTRACT", "HEARTBEAT_FRESH_SECONDS", "MAX_POLL_INTERVAL", "MIN_POLL_INTERVAL", "create_worker_state", "load_worker_state", "request_worker_action", "run_runtime_worker", "run_worker_iteration", "save_worker_state", "seal_worker_state", "validate_worker_state", "worker_health"]
