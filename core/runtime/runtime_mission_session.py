from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from core.runtime.runtime_operator_session import fingerprint, parse_time, time_text

CONTRACT = "zero.runtime.mission_session.v1"
STATUSES = {"created", "starting", "running", "idle", "paused", "recovering", "resuming", "completed", "blocked", "failed", "stopping", "stopped"}
PHASES = {"mission_loaded", "goal_graph_ready", "execution_registered", "scheduler_ready", "worker_ready", "replanning_ready", "daemon_ready", "runtime_running", "runtime_idle", "runtime_blocked", "runtime_completed", "runtime_stopped"}
DEFAULT_CONFIG = {"mission_session_resume_enabled": True, "mission_session_auto_resume": True, "mission_session_resume_max_attempts": 3, "mission_session_recover_blocked": True, "mission_session_recover_failed": False, "mission_session_replay_protection": True}
PATH_FIELDS = ("mission_state_path", "goal_graph_state_path", "execution_registry_state_path", "scheduler_state_path", "worker_state_path", "replanning_engine_state_path", "daemon_state_path", "event_bus_state_path")

def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}

def _unsigned(value: Mapping[str, Any]) -> dict[str, Any]:
    result = _mapping(value); result.pop("session_fingerprint", None); return result

def _unsafe(path: Path) -> bool:
    try:
        attrs = getattr(path.lstat(), "st_file_attributes", 0)
        return path.is_symlink() or bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except OSError:
        return False

def _path(value: Any) -> str:
    return str(Path(value).resolve(strict=False)) if value is not None and str(value).strip() else ""

def _checkpoint(phase: str, now: Any = None) -> dict[str, Any]:
    at = time_text(now)
    return {"phase": phase, "previous_phase": None, "loop_iteration": 0, "daemon_loop_iteration": 0, "scheduler_status": None, "worker_status": None, "replanning_status": None, "mission_status": None, "execution_status": None, "last_event_id": None, "last_event_sequence": 0, "last_dispatch_id": None, "last_worker_execution_id": None, "last_replanning_iteration": 0, "checkpoint_created_at": at, "checkpoint_updated_at": at, "resume_required": False, "resume_reason": None}

def seal_mission_session_state(state: Mapping[str, Any]) -> dict[str, Any]:
    value = _unsigned(state); value["session_fingerprint"] = fingerprint(value); return value

def create_mission_session_state(*, mission_id: str, goal_id: str, execution_id: str, session_state_path: Any = None, session_name: str = "mission-runtime", mission_state_path: Any, goal_graph_state_path: Any = None, execution_registry_state_path: Any, scheduler_state_path: Any, worker_state_path: Any, replanning_engine_state_path: Any, daemon_state_path: Any, event_bus_state_path: Any, target_root: Any, workspace_root: Any, runtime_config: Mapping[str, Any] | None = None, now: Any = None) -> dict[str, Any]:
    identities = {"mission_id": str(mission_id or "").strip(), "goal_id": str(goal_id or "").strip(), "execution_id": str(execution_id or "").strip()}
    if not all(identities.values()): raise ValueError("mission_session_identity_required")
    paths = {"mission_state_path": _path(mission_state_path), "goal_graph_state_path": _path(goal_graph_state_path or mission_state_path), "execution_registry_state_path": _path(execution_registry_state_path), "scheduler_state_path": _path(scheduler_state_path), "worker_state_path": _path(worker_state_path), "replanning_engine_state_path": _path(replanning_engine_state_path), "daemon_state_path": _path(daemon_state_path), "event_bus_state_path": _path(event_bus_state_path)}
    at = time_text(now); config = {**DEFAULT_CONFIG, **_mapping(runtime_config)}
    seed = {**identities, "session_state_path": _path(session_state_path) if session_state_path else paths["mission_state_path"], "target_root": _path(target_root), "workspace_root": _path(workspace_root)}
    session_id = f"mission-session-{fingerprint(seed)[:20]}"
    state = {"contract": CONTRACT, "session_id": session_id, **identities, "session_name": str(session_name or "mission-runtime").strip(), "session_status": "created", "created_at": at, "started_at": None, "updated_at": at, "last_heartbeat_at": at, "completed_at": None, "failed_at": None, "resume_count": 0, "recovery_count": 0, "failure_count": 0, "last_resume_at": None, "last_recovery_at": None, "current_phase": "mission_loaded", "last_completed_phase": None, "next_phase": "goal_graph_ready", **paths, "target_root": _path(target_root), "workspace_root": _path(workspace_root), "runtime_config": config, "session_checkpoint": _checkpoint("mission_loaded", now), "last_result": None, "failure": None, "audit_record": {"event_type": "mission_session_created", "created_at": at}}
    return seal_mission_session_state(state)

def normalize_mission_session_state(state: Mapping[str, Any], *, now: Any = None) -> dict[str, Any]:
    value = _mapping(state)
    if value.get("contract") != CONTRACT: raise ValueError("invalid_mission_session_contract")
    if value.get("session_fingerprint") != fingerprint(_unsigned(value)): raise ValueError("mission_session_fingerprint_mismatch")
    changed = False
    for key, default in (("runtime_config", DEFAULT_CONFIG), ("resume_count", 0), ("recovery_count", 0), ("failure_count", 0)):
        if key not in value: value[key] = deepcopy(default); changed = True
    if not isinstance(value.get("session_checkpoint"), Mapping): value["session_checkpoint"] = _checkpoint(str(value.get("current_phase") or "mission_loaded"), now); changed = True
    return seal_mission_session_state(value) if changed else value

def validate_mission_session_state(state: Mapping[str, Any]) -> list[str]:
    value = _mapping(state); reasons = []
    if value.get("contract") != CONTRACT: reasons.append("invalid_mission_session_contract")
    if value.get("session_fingerprint") != fingerprint(_unsigned(value)): reasons.append("mission_session_fingerprint_mismatch")
    for field in ("session_id", "mission_id", "goal_id", "execution_id", "session_name", "target_root", "workspace_root", *PATH_FIELDS):
        if not str(value.get(field) or "").strip(): reasons.append(f"{field}_required")
    if value.get("session_status") not in STATUSES: reasons.append("invalid_mission_session_status")
    if value.get("current_phase") not in PHASES: reasons.append("invalid_mission_session_phase")
    checkpoint = value.get("session_checkpoint")
    if not isinstance(checkpoint, Mapping) or checkpoint.get("phase") not in PHASES: reasons.append("invalid_session_checkpoint")
    return reasons

def save_mission_session_state(state: Mapping[str, Any], path: Any) -> dict[str, Any]:
    destination = Path(path)
    if destination.exists() and _unsafe(destination): raise ValueError("unsafe_mission_session_state_path")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if _unsafe(destination.parent): raise ValueError("unsafe_mission_session_state_directory")
    value = seal_mission_session_state(state); reasons = validate_mission_session_state(value)
    if reasons: raise ValueError(";".join(reasons))
    temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, destination); return value

def load_mission_session_state(path: Any) -> dict[str, Any]:
    source = Path(path)
    if _unsafe(source): raise ValueError("unsafe_mission_session_state_path")
    try: raw = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ValueError("invalid_mission_session_json") from exc
    value = normalize_mission_session_state(raw); reasons = validate_mission_session_state(value)
    if reasons: raise ValueError(";".join(reasons))
    if value != raw: save_mission_session_state(value, source)
    return value

def _save_transition(state: Mapping[str, Any], path: Any, phase: str, *, status: str | None = None, now: Any = None, before: bool = False, **evidence: Any) -> dict[str, Any]:
    value = _mapping(state); old = str(value.get("current_phase") or "mission_loaded"); cp = _mapping(value.get("session_checkpoint")); at = time_text(now)
    cp.update({"previous_phase": old, "phase": phase, "checkpoint_updated_at": at, **deepcopy(evidence)})
    if before: cp["resume_required"] = True; cp["resume_reason"] = f"interrupted_before_{phase}"
    else: cp["resume_required"] = False; cp["resume_reason"] = None; value["last_completed_phase"] = phase
    value.update(current_phase=phase, next_phase=None, updated_at=at, last_heartbeat_at=at, session_checkpoint=cp)
    if status: value["session_status"] = status
    return save_mission_session_state(value, path)

def _publish(state: Mapping[str, Any], topic: str, path: Any, *, now: Any = None) -> dict[str, Any]:
    value = _mapping(state); bus_path = Path(value["event_bus_state_path"])
    if not bus_path.exists(): return value
    try:
        from core.runtime.runtime_event_bus import load_event_bus_state, publish, save_event_bus_state
        bus = load_event_bus_state(bus_path); cp = _mapping(value.get("session_checkpoint")); number = int(cp.get("daemon_loop_iteration") or cp.get("loop_iteration") or 0)
        bus, event = publish(bus, event_type="mission", topic=topic, source=value["session_id"], payload={"session_id": value["session_id"], "mission_id": value["mission_id"], "session_status": value["session_status"], "phase": value["current_phase"]}, idempotency_key=f"{value['session_id']}:{topic}:{value['current_phase']}:{number}", correlation_id=value["mission_id"], now=now)
        save_event_bus_state(bus, bus_path); cp["last_event_id"] = event.get("event_id"); cp["last_event_sequence"] = int(event.get("sequence") or 0); value["session_checkpoint"] = cp
    except Exception as exc:
        value.setdefault("audit_record", {})["last_event_publish_error"] = str(exc)
    return save_mission_session_state(value, path)

def _prepare(state: Mapping[str, Any], session_path: Any, *, now: Any = None) -> dict[str, Any]:
    value = _mapping(state)
    from core.runtime.runtime_mission_model import load_mission
    mission = load_mission(value["mission_state_path"], check_expiry=False)
    value = _save_transition(value, session_path, "goal_graph_ready", now=now, before=True)
    if not isinstance(mission.get("goal_graph"), Mapping): raise ValueError("mission_goal_graph_required")
    value = _save_transition(value, session_path, "goal_graph_ready", now=now, mission_status=mission.get("mission_status"))
    value = _save_transition(value, session_path, "execution_registered", now=now, before=True)
    registry_path = Path(value["execution_registry_state_path"])
    if not registry_path.exists():
        from core.runtime.runtime_mission_execution_registry_bridge import sync_mission_execution_registry
        sync_mission_execution_registry(mission, target_root=value["target_root"], workspace_root=value["workspace_root"], runtime_config=value["runtime_config"], registry_path=registry_path, now=now)
    value = _save_transition(value, session_path, "execution_registered", now=now, execution_status="registered")
    from core.runtime.runtime_mission_scheduler import create_mission_scheduler_state, save_mission_scheduler_state, load_mission_scheduler_state, enqueue_mission
    value = _save_transition(value, session_path, "scheduler_ready", now=now, before=True); p = Path(value["scheduler_state_path"])
    if p.exists(): scheduler = load_mission_scheduler_state(p)
    else: scheduler = save_mission_scheduler_state(create_mission_scheduler_state(state_path=p, scheduler_name=value["session_name"], now=now), p)
    if not any(str(e.get("mission_id")) == value["mission_id"] for e in _mapping(scheduler.get("entries")).values()): scheduler = save_mission_scheduler_state(enqueue_mission(scheduler, value["mission_state_path"], now=now), p)
    value = _save_transition(value, session_path, "scheduler_ready", now=now, scheduler_status=scheduler.get("scheduler_status"))
    from core.runtime.runtime_worker_service import create_worker_state, save_worker_state, load_worker_state
    value = _save_transition(value, session_path, "worker_ready", now=now, before=True); p = Path(value["worker_state_path"])
    worker_scheduler_path = mission.get("scheduler_state_path") or value["scheduler_state_path"]
    worker = load_worker_state(p) if p.exists() else save_worker_state(create_worker_state(scheduler_state_path=worker_scheduler_path, worker_state_path=p, worker_name=value["session_name"], target_root=value["target_root"], now=now), p)
    value = _save_transition(value, session_path, "worker_ready", now=now, worker_status=worker.get("worker_status"))
    from core.runtime.runtime_event_bus import create_event_bus_state, save_event_bus_state, load_event_bus_state
    p = Path(value["event_bus_state_path"]); load_event_bus_state(p) if p.exists() else save_event_bus_state(create_event_bus_state(state_path=p, bus_name=value["session_name"], now=now), p)
    from core.runtime.runtime_replanning_engine import create_replanning_engine_state, save_replanning_engine_state, load_replanning_engine_state
    value = _save_transition(value, session_path, "replanning_ready", now=now, before=True); p = Path(value["replanning_engine_state_path"])
    engine = load_replanning_engine_state(p) if p.exists() else save_replanning_engine_state(create_replanning_engine_state(state_path=p, event_bus_state_path=value["event_bus_state_path"], engine_name=value["session_name"], now=now), p)
    value = _save_transition(value, session_path, "replanning_ready", now=now, replanning_status=engine.get("engine_status"))
    from core.runtime.runtime_mission_daemon import create_mission_daemon_state, save_mission_daemon_state, load_mission_daemon_state
    value = _save_transition(value, session_path, "daemon_ready", now=now, before=True); p = Path(value["daemon_state_path"])
    daemon = load_mission_daemon_state(p) if p.exists() else save_mission_daemon_state(create_mission_daemon_state(state_path=p, daemon_name=value["session_name"], scheduler_state_path=value["scheduler_state_path"], worker_state_path=value["worker_state_path"], worker_name=value["session_name"], target_root=value["target_root"], workspace_root=value["workspace_root"], now=now), p)
    if not daemon.get("replanning_engine_state_path"):
        daemon["replanning_engine_state_path"] = value["replanning_engine_state_path"]; daemon = save_mission_daemon_state(daemon, p)
    return _save_transition(value, session_path, "daemon_ready", now=now, daemon_loop_iteration=int(daemon.get("loop_iteration") or 0))

def run_mission_session_iteration(session_state_path: Any, *, runtime_config: Mapping[str, Any] | None = None, now: Any = None) -> dict[str, Any]:
    value = load_mission_session_state(session_state_path)
    if value["session_status"] in {"completed", "paused", "stopped"}: return value
    if value["session_status"] == "created":
        value["started_at"] = time_text(now); value["session_status"] = "starting"; value = save_mission_session_state(value, session_state_path); value = _publish(value, "mission_session.started", session_state_path, now=now)
    value = _prepare(value, session_state_path, now=now)
    value = _save_transition(value, session_state_path, "runtime_running", status="running", now=now, before=True)
    from core.runtime.runtime_mission_daemon import run_mission_daemon_iteration
    config = {**_mapping(value["runtime_config"]), **_mapping(runtime_config), "event_bus_state_path": value["event_bus_state_path"], "replanning_engine_state_path": value["replanning_engine_state_path"]}
    try: daemon = run_mission_daemon_iteration(daemon_state_path=value["daemon_state_path"], runtime_config=config, now=now)
    except Exception as exc:
        value.update(session_status="failed", failed_at=time_text(now), failure={"critical": True, "reason": str(exc)}, failure_count=int(value.get("failure_count") or 0)+1); value = _save_transition(value, session_state_path, "runtime_blocked", status="failed", now=now); return _publish(value, "mission_session.failed", session_state_path, now=now)
    ds = daemon.get("daemon_status"); phase, status, topic = ("runtime_stopped", "stopped", "mission_session.stopped") if ds == "stopped" else (("runtime_blocked", "blocked", "mission_session.blocked") if ds in {"blocked", "failed"} else ("runtime_idle", "idle", "mission_session.idle"))
    from core.runtime.runtime_mission_model import load_mission
    mission = load_mission(value["mission_state_path"], check_expiry=False)
    if mission.get("mission_status") == "completed": phase, status, topic = "runtime_completed", "completed", "mission_session.completed"
    value["completed_at"] = time_text(now) if status == "completed" else value.get("completed_at")
    value = _save_transition(value, session_state_path, phase, status=status, now=now, daemon_loop_iteration=int(daemon.get("loop_iteration") or 0), scheduler_status=daemon.get("last_scheduler_status"), replanning_status=daemon.get("last_replanning_status"), mission_status=mission.get("mission_status"), last_event_id=daemon.get("last_event_id"))
    evidence = {key: value[key] for key in PATH_FIELDS}; value["last_result"] = {"session_id": value["session_id"], "mission_id": value["mission_id"], "goal_id": value["goal_id"], "execution_id": value["execution_id"], "session_status": status, "mission_status": mission.get("mission_status"), "scheduler_status": daemon.get("last_scheduler_status"), "worker_status": None, "replanning_status": daemon.get("last_replanning_status"), "daemon_status": ds, "completed_phases": [value.get("last_completed_phase")], "resume_count": value["resume_count"], "recovery_count": value["recovery_count"], "started_at": value["started_at"], "completed_at": value["completed_at"], "failure": value.get("failure"), "evidence_paths": evidence}; value = save_mission_session_state(value, session_state_path)
    return _publish(value, topic, session_state_path, now=now)

def converge_completed_mission_session(session_state_path: Any, *, now: Any = None) -> dict[str, Any]:
    value = load_mission_session_state(session_state_path)
    if value["session_status"] == "completed":
        return value

    from core.runtime.runtime_mission_model import load_mission
    mission = load_mission(value["mission_state_path"], check_expiry=False)
    if mission.get("mission_status") != "completed" or mission.get("failed_goal_ids") or mission.get("blocked_goal_ids"):
        raise ValueError("mission_not_safely_completed")

    value = run_mission_session_iteration(session_state_path, now=now)
    if value.get("session_status") != "completed":
        raise ValueError("mission_session_completion_failed")

    sessions = {}
    from core.runtime.runtime_operator_session import load_runtime_session
    for goal_id in mission.get("goal_order") or []:
        goal = _mapping(_mapping(mission.get("goals")).get(goal_id))
        sessions[goal_id] = load_runtime_session(goal["session_path"], target_root=value["target_root"], now=now)

    from core.runtime.runtime_goal_execution_registry import finalize_goal_execution_registry, load_goal_execution_registry, save_goal_execution_registry
    registry = load_goal_execution_registry(value["execution_registry_state_path"])
    registry = finalize_goal_execution_registry(registry, mission=mission, sessions=sessions, now=now)
    save_goal_execution_registry(registry, value["execution_registry_state_path"])

    from core.runtime.runtime_event_bus import load_event_bus_state, publish, save_event_bus_state
    bus = load_event_bus_state(value["event_bus_state_path"])
    for goal_id in mission.get("goal_order") or []:
        session = sessions[goal_id]
        tx = _mapping(_mapping(session.get("artifacts")).get("transaction_result"))
        bus, _ = publish(bus, event_type="mission", topic="mission_execution.transaction_completed", source=value["session_id"], payload={"mission_id": mission["mission_id"], "goal_id": goal_id, "session_id": session.get("session_id"), "transaction_status": tx.get("transaction_status")}, idempotency_key=f"{mission['mission_id']}:{goal_id}:transaction_completed", correlation_id=mission["mission_id"], now=now)
        bus, _ = publish(bus, event_type="mission", topic="mission_goal.completed", source=value["session_id"], payload={"mission_id": mission["mission_id"], "goal_id": goal_id, "session_id": session.get("session_id"), "goal_status": "completed"}, idempotency_key=f"{mission['mission_id']}:{goal_id}:completed", correlation_id=mission["mission_id"], now=now)
    bus, _ = publish(bus, event_type="mission", topic="mission.completed", source=value["session_id"], payload={"mission_id": mission["mission_id"], "completed_goal_ids": deepcopy(mission.get("completed_goal_ids") or [])}, idempotency_key=f"{mission['mission_id']}:completed", correlation_id=mission["mission_id"], now=now)
    save_event_bus_state(bus, value["event_bus_state_path"])

    from core.runtime.runtime_mission_scheduler import load_mission_scheduler_state, request_mission_scheduler_action, run_mission_scheduler_iteration, save_mission_scheduler_state
    scheduler = load_mission_scheduler_state(value["scheduler_state_path"])
    scheduler = save_mission_scheduler_state(request_mission_scheduler_action(scheduler, "stop", now=now), value["scheduler_state_path"])
    scheduler = run_mission_scheduler_iteration(scheduler_state_path=value["scheduler_state_path"], worker_state_path=value["worker_state_path"], worker_name=value["session_name"], target_root=value["target_root"], workspace_root=value["workspace_root"], runtime_config={"event_bus_state_path": value["event_bus_state_path"]}, now=now)

    from core.runtime.runtime_worker_service import load_worker_state, request_worker_action, run_worker_iteration, save_worker_state
    worker = load_worker_state(value["worker_state_path"])
    worker = save_worker_state(request_worker_action(worker, "stop", now=now), value["worker_state_path"])
    worker = run_worker_iteration(scheduler_state_path=worker["scheduler_state_path"], worker_state_path=value["worker_state_path"], worker_name=worker["worker_name"], target_root=value["target_root"], workspace_root=value["workspace_root"], now=now, runtime_config={"event_bus_state_path": value["event_bus_state_path"]})

    from core.runtime.runtime_mission_daemon import load_mission_daemon_state, request_mission_daemon_action, run_mission_daemon_iteration, save_mission_daemon_state
    daemon = load_mission_daemon_state(value["daemon_state_path"])
    daemon = save_mission_daemon_state(request_mission_daemon_action(daemon, "stop", now=now), value["daemon_state_path"])
    daemon = run_mission_daemon_iteration(daemon_state_path=value["daemon_state_path"], runtime_config={"event_bus_state_path": value["event_bus_state_path"], "replanning_engine_state_path": value["replanning_engine_state_path"]}, now=now)

    checkpoint = _mapping(value.get("session_checkpoint"))
    checkpoint.update(mission_status="completed", execution_status="completed", scheduler_status=scheduler.get("scheduler_status"), worker_status=worker.get("worker_status"), daemon_status=daemon.get("daemon_status"), resume_required=False, resume_reason=None)
    evidence_paths = {key: value[key] for key in PATH_FIELDS}
    value.update(session_status="completed", current_phase="runtime_completed", last_completed_phase="runtime_completed", next_phase=None, execution_status="completed", completed_at=value.get("completed_at") or time_text(now), failure=None, resume_required=False, stop_requested=False, status="completed", mutation_performed=False, replayed=False, session_checkpoint=checkpoint)
    value["last_result"] = {"session_id": value["session_id"], "mission_id": value["mission_id"], "goal_id": value["goal_id"], "execution_id": value["execution_id"], "status": "completed", "session_status": "completed", "mission_status": "completed", "execution_status": "completed", "scheduler_status": scheduler.get("scheduler_status"), "worker_status": worker.get("worker_status"), "daemon_status": daemon.get("daemon_status"), "completed_goal_ids": deepcopy(mission.get("completed_goal_ids") or []), "completed_phases": ["runtime_completed"], "resume_count": value["resume_count"], "recovery_count": value["recovery_count"], "started_at": value["started_at"], "completed_at": value["completed_at"], "failure": None, "mutation_performed": False, "replayed": False, "evidence_paths": evidence_paths}
    return save_mission_session_state(value, session_state_path)

def run_mission_session(session_state_path: Any, *, max_iterations: int = 1, runtime_config: Mapping[str, Any] | None = None, now: Any = None) -> dict[str, Any]:
    if isinstance(max_iterations, bool) or max_iterations < 1: raise ValueError("invalid_mission_session_max_iterations")
    value = load_mission_session_state(session_state_path)
    for _ in range(max_iterations):
        value = run_mission_session_iteration(session_state_path, runtime_config=runtime_config, now=now)
        if value["session_status"] in {"completed", "blocked", "failed", "paused", "stopped"}: break
    return value

def resume_mission_session(session_state_path: Any, *, explicit: bool = False, max_iterations: int = 1, runtime_config: Mapping[str, Any] | None = None, now: Any = None) -> dict[str, Any]:
    value = load_mission_session_state(session_state_path); config = {**_mapping(value.get("runtime_config")), **_mapping(runtime_config)}; status = value["session_status"]
    if status == "completed": return value
    if status in {"paused", "stopped"} and not explicit: return value
    if status == "failed" and (bool(_mapping(value.get("failure")).get("critical")) or not config.get("mission_session_recover_failed", False)): return value
    if status == "blocked" and not config.get("mission_session_recover_blocked", True): return value
    if not config.get("mission_session_resume_enabled", True): return value
    if int(value.get("resume_count") or 0) >= int(config.get("mission_session_resume_max_attempts", 3)): raise ValueError("mission_session_resume_attempts_exhausted")
    from core.runtime.runtime_mission_daemon import load_mission_daemon_state, request_mission_daemon_action, save_mission_daemon_state
    daemon = load_mission_daemon_state(value["daemon_state_path"]) if Path(value["daemon_state_path"]).exists() else None
    if daemon and daemon.get("stop_requested") and not explicit: return value
    if daemon and explicit and status in {"paused", "stopped"}: save_mission_daemon_state(request_mission_daemon_action(daemon, "resume", now=now), value["daemon_state_path"])
    value.update(session_status="resuming", resume_count=int(value.get("resume_count") or 0)+1, last_resume_at=time_text(now)); value = save_mission_session_state(value, session_state_path); value = _publish(value, "mission_session.resuming", session_state_path, now=now)
    result = run_mission_session(session_state_path, max_iterations=max_iterations, runtime_config=config, now=now)
    return _publish(result, "mission_session.resumed", session_state_path, now=now)

def mission_session_health(state_or_path: Any, *, now: Any = None, stale_after_seconds: int = 90) -> dict[str, Any]:
    try: value = load_mission_session_state(state_or_path) if isinstance(state_or_path, (str, Path)) else normalize_mission_session_state(state_or_path)
    except ValueError as exc: return {"healthy": False, "status": "invalid", "reasons": [str(exc)]}
    reasons = validate_mission_session_state(value); heartbeat = parse_time(value.get("last_heartbeat_at")); current = parse_time(now) if now is not None else datetime.now(timezone.utc)
    if value["session_status"] in {"running", "starting", "recovering", "resuming"} and heartbeat and (current-heartbeat).total_seconds() > stale_after_seconds: reasons.append("stale_heartbeat")
    if value["session_status"] == "blocked": reasons.append("blocked_recovery")
    if value["session_status"] == "failed": reasons.append("failed_recovery")
    return {"healthy": not reasons, "status": value["session_status"], "session_id": value["session_id"], "current_phase": value["current_phase"], "resume_required": bool(_mapping(value.get("session_checkpoint")).get("resume_required")), "reasons": reasons}

__all__ = ["converge_completed_mission_session", "create_mission_session_state", "load_mission_session_state", "mission_session_health", "normalize_mission_session_state", "resume_mission_session", "run_mission_session", "run_mission_session_iteration", "save_mission_session_state", "seal_mission_session_state", "validate_mission_session_state"]
