from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import time
from typing import Any, Callable, Mapping

from core.runtime.runtime_mission_scheduler import (
    run_mission_scheduler_iteration,
)
from core.runtime.runtime_operator_session import (
    fingerprint,
    parse_time,
    time_text,
)
from core.runtime.runtime_mission_daemon_recovery import (
    ITERATION_PHASES, RECOVERY_STATUSES, normalize_recovery_state,
    recovery_decision, recovery_event_payload, validate_iteration_checkpoint,
)

CONTRACT = "zero.runtime.mission_daemon.v1"

MIN_POLL_INTERVAL = 0.1
MAX_POLL_INTERVAL = 60.0
HEARTBEAT_FRESH_SECONDS = 90

VALID_STATUSES = {
    "created",
    "starting",
    "running",
    "idle",
    "paused",
    "stopping",
    "stopped",
    "blocked",
    "failed",
}


def _mapping(value: Any) -> dict[str, Any]:
    return (
        deepcopy(dict(value))
        if isinstance(value, Mapping)
        else {}
    )


def _unsigned(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    result = _mapping(value)
    result.pop("daemon_fingerprint", None)
    return result


def _unsafe(path: Path) -> bool:
    try:
        attributes = getattr(
            path.lstat(),
            "st_file_attributes",
            0,
        )
        reparse = getattr(
            stat,
            "FILE_ATTRIBUTE_REPARSE_POINT",
            0x400,
        )
        return path.is_symlink() or bool(
            attributes & reparse
        )
    except OSError:
        return False


def _atomic_write_json(
    value: Mapping[str, Any],
    destination: Path,
) -> None:
    if destination.exists() and _unsafe(destination):
        raise ValueError("unsafe_mission_daemon_state_path")

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    if _unsafe(destination.parent):
        raise ValueError(
            "unsafe_mission_daemon_state_directory"
        )

    temporary = destination.with_name(
        f".{destination.name}.tmp"
    )
    with temporary.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        handle.write(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())

    os.replace(temporary, destination)


def seal_mission_daemon_state(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    value = _unsigned(state)
    value["daemon_fingerprint"] = fingerprint(value)
    return value


def validate_mission_daemon_state(
    state: Mapping[str, Any],
) -> list[str]:
    value = _mapping(state)
    reasons: list[str] = []

    if value.get("contract") != CONTRACT:
        reasons.append(
            "invalid_mission_daemon_contract"
        )

    expected = fingerprint(_unsigned(value))
    if value.get("daemon_fingerprint") != expected:
        reasons.append(
            "mission_daemon_fingerprint_mismatch"
        )

    if not str(value.get("daemon_id") or "").strip():
        reasons.append("mission_daemon_id_required")
    if not str(value.get("daemon_name") or "").strip():
        reasons.append("mission_daemon_name_required")

    if value.get("daemon_status") not in VALID_STATUSES:
        reasons.append(
            "invalid_mission_daemon_status"
        )

    if value.get("recovery_status") not in RECOVERY_STATUSES:
        reasons.append("invalid_recovery_status")
    if value.get("iteration_phase") not in ITERATION_PHASES:
        reasons.append("invalid_iteration_phase")
    for field in ("recovery_attempts", "recovery_failures", "last_completed_loop_iteration",
                  "last_scheduler_completed_iteration", "last_replanning_completed_iteration",
                  "last_published_event_iteration"):
        item = value.get(field)
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            reasons.append(f"invalid_{field}")

    for field in (
        "scheduler_state_path",
        "worker_state_path",
        "target_root",
        "workspace_root",
        "state_path",
    ):
        if not str(value.get(field) or "").strip():
            reasons.append(f"{field}_required")

    replanning_path = value.get(
        "replanning_engine_state_path"
    )
    if (
        replanning_path is not None
        and not str(replanning_path).strip()
    ):
        reasons.append(
            "invalid_replanning_engine_state_path"
        )

    return reasons


def create_mission_daemon_state(
    *,
    state_path: Any,
    daemon_name: str,
    scheduler_state_path: Any,
    worker_state_path: Any,
    worker_name: str,
    target_root: Any,
    workspace_root: Any,
    owner: str = "mission-runtime",
    now: Any = None,
) -> dict[str, Any]:
    name = str(daemon_name or "").strip()
    if not name:
        raise ValueError("mission_daemon_name_required")

    worker = str(worker_name or "").strip()
    if not worker:
        raise ValueError("worker_name_required")

    owner_text = str(owner or "").strip()
    if not owner_text:
        raise ValueError(
            "mission_daemon_owner_required"
        )

    destination = Path(state_path)
    at = time_text(now)

    identity = {
        "daemon_name": name,
        "state_path": str(
            destination.resolve(strict=False)
        ).replace("\\", "/").casefold(),
        "scheduler_state_path": str(
            Path(scheduler_state_path).resolve(
                strict=False
            )
        ).replace("\\", "/").casefold(),
        "worker_state_path": str(
            Path(worker_state_path).resolve(
                strict=False
            )
        ).replace("\\", "/").casefold(),
    }

    return seal_mission_daemon_state(
        {
            "contract": CONTRACT,
            "daemon_id": (
                "mission-daemon-"
                f"{fingerprint(identity)[:20]}"
            ),
            "daemon_name": name,
            "daemon_status": "created",
            "state_path": str(
                destination.resolve(strict=False)
            ),
            "scheduler_state_path": str(
                Path(scheduler_state_path).resolve(
                    strict=False
                )
            ),
            "worker_state_path": str(
                Path(worker_state_path).resolve(
                    strict=False
                )
            ),
            "replanning_engine_state_path": None,
            "worker_name": worker,
            "target_root": str(
                Path(target_root).resolve(
                    strict=False
                )
            ),
            "workspace_root": str(
                Path(workspace_root).resolve(
                    strict=False
                )
            ),
            "owner": owner_text,
            "created_at": at,
            "started_at": None,
            "updated_at": at,
            "last_heartbeat_at": at,
            "stopped_at": None,
            "loop_iteration": 0,
            "successful_iterations": 0,
            "idle_iterations": 0,
            "blocked_iterations": 0,
            "failed_iterations": 0,
            "stop_requested": False,
            "pause_requested": False,
            "last_scheduler_status": None,
            "last_scheduler_result": None,
            "last_replanning_status": None,
            "last_replanning_result": None,
            "replanning_iterations": 0,
            "replanning_failures": 0,
            "last_event_id": None,
            "failure": None,
            "recovery_status": "not_required",
            "recovery_attempts": 0,
            "recovery_failures": 0,
            "last_recovery_at": None,
            "last_recovery_result": None,
            "previous_daemon_status": None,
            "iteration_phase": "idle",
            "iteration_checkpoint": {},
            "last_completed_loop_iteration": 0,
            "last_scheduler_completed_iteration": 0,
            "last_replanning_completed_iteration": 0,
            "last_published_event_iteration": 0,
            "last_published_event_topic": None,
            "last_published_event_id": None,
            "audit_record": {
                "event_type": (
                    "runtime_mission_daemon_created"
                ),
                "created_at": at,
            },
        }
    )


def save_mission_daemon_state(
    state: Mapping[str, Any],
    path: Any,
) -> dict[str, Any]:
    destination = Path(path)
    value = seal_mission_daemon_state(state)
    reasons = validate_mission_daemon_state(value)
    if reasons:
        raise ValueError(";".join(reasons))
    _atomic_write_json(value, destination)
    return value


def load_mission_daemon_state(
    path: Any,
) -> dict[str, Any]:
    source = Path(path)
    if _unsafe(source):
        raise ValueError(
            "unsafe_mission_daemon_state_path"
        )

    try:
        value = json.loads(
            source.read_text(
                encoding="utf-8-sig"
            )
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError(
            "invalid_mission_daemon_json"
        ) from exc

    # Normalize legacy v1 states before validation; sealing happens only after
    # the original fingerprint has established that the persisted state is authentic.
    legacy_reasons = []
    if isinstance(value, Mapping) and value.get("daemon_fingerprint") != fingerprint(_unsigned(value)):
        legacy_reasons.append("mission_daemon_fingerprint_mismatch")
    if legacy_reasons:
        raise ValueError(";".join(legacy_reasons))
    value, migrated = normalize_recovery_state(value)
    if migrated:
        value = seal_mission_daemon_state(value)
        _atomic_write_json(value, source)
    reasons = validate_mission_daemon_state(value)
    if reasons:
        raise ValueError(";".join(reasons))
    return value


def _publish_daemon_event(
    runtime_config: Mapping[str, Any] | None,
    *,
    topic: str,
    source: str,
    payload: Mapping[str, Any],
    idempotency_key: str,
    now: Any = None,
) -> dict[str, Any] | None:
    config = _mapping(runtime_config)
    state_path_text = str(
        config.get("event_bus_state_path") or ""
    ).strip()
    if not state_path_text:
        return None

    from core.runtime.runtime_event_bus import (
        load_event_bus_state,
        publish,
        save_event_bus_state,
    )

    state_path = Path(state_path_text)
    bus = load_event_bus_state(state_path)
    bus, event = publish(
        bus,
        event_type="daemon",
        topic=topic,
        source=source,
        payload=payload,
        idempotency_key=idempotency_key,
        correlation_id=str(
            payload.get("daemon_id") or ""
        )
        or None,
        now=now,
    )
    save_event_bus_state(bus, state_path)
    return event


def _run_replanning_iteration(
    state: Mapping[str, Any],
    runtime_config: Mapping[str, Any] | None,
    *,
    now: Any = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    value = _mapping(state)
    config = _mapping(runtime_config)
    replanning_path_text = str(
        config.get("replanning_engine_state_path")
        or value.get("replanning_engine_state_path")
        or ""
    ).strip()

    if not replanning_path_text:
        return value, None

    from core.runtime.runtime_replanning_engine import (
        run_replanning_engine_iteration,
    )

    result = run_replanning_engine_iteration(
        engine_state_path=replanning_path_text,
        max_events=int(
            config.get("replanning_max_events") or 100
        ),
        now=now,
    )

    value["replanning_engine_state_path"] = str(
        Path(replanning_path_text).resolve(
            strict=False
        )
    )
    value["last_replanning_status"] = result.get(
        "engine_status"
    )
    value["last_replanning_result"] = {
        "engine_id": result.get("engine_id"),
        "engine_status": result.get(
            "engine_status"
        ),
        "processed_event_count": result.get(
            "processed_event_count"
        ),
        "ignored_event_count": result.get(
            "ignored_event_count"
        ),
        "last_processed_sequence": result.get(
            "last_processed_sequence"
        ),
        "last_event_id": result.get(
            "last_event_id"
        ),
        "retry_count": result.get("retry_count"),
        "redispatch_count": result.get(
            "redispatch_count"
        ),
        "replan_count": result.get(
            "replan_count"
        ),
        "manual_review_count": result.get(
            "manual_review_count"
        ),
        "complete_count": result.get(
            "complete_count"
        ),
    }
    value["replanning_iterations"] = int(
        value.get("replanning_iterations") or 0
    ) + 1
    return value, result


def _heartbeat(
    state: Mapping[str, Any],
    status: str,
    *,
    now: Any = None,
) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(
            "invalid_mission_daemon_status"
        )

    value = _mapping(state)
    at = time_text(now)
    value["daemon_status"] = status
    value["updated_at"] = at
    value["last_heartbeat_at"] = at
    return seal_mission_daemon_state(value)


def request_mission_daemon_action(
    state: Mapping[str, Any],
    action: str,
    *,
    now: Any = None,
) -> dict[str, Any]:
    value = _mapping(state)

    if action == "pause":
        value["pause_requested"] = True
        status = "paused"
    elif action == "resume":
        value["pause_requested"] = False
        value["stop_requested"] = False
        status = "idle"
    elif action == "stop":
        value["stop_requested"] = True
        status = "stopping"
    else:
        raise ValueError(
            "invalid_mission_daemon_action"
        )

    return _heartbeat(
        value,
        status,
        now=now,
    )


def _checkpoint(state: Mapping[str, Any], path: Any, phase: str, *, now: Any = None,
                **updates: Any) -> dict[str, Any]:
    value = _mapping(state)
    checkpoint = _mapping(value.get("iteration_checkpoint"))
    checkpoint.setdefault("loop_iteration", int(value.get("loop_iteration") or 0))
    checkpoint.update(deepcopy(updates))
    checkpoint["checkpoint_updated_at"] = time_text(now)
    value["iteration_phase"] = phase
    value["iteration_checkpoint"] = checkpoint
    return save_mission_daemon_state(value, path)


def _recover_mission_daemon(state: Mapping[str, Any], path: Any,
                            runtime_config: Mapping[str, Any] | None, *, now: Any = None) -> dict[str, Any]:
    value = _mapping(state)
    decision = recovery_decision(value, runtime_config)
    if not decision["required"]:
        return value
    value["previous_daemon_status"] = value.get("daemon_status")
    if not decision["recoverable"]:
        value["recovery_status"] = "blocked"
        value["last_recovery_result"] = {"recovered": False, "reason": ",".join(decision["reasons"]),
                                         "resumed_from_phase": value.get("iteration_phase"),
                                         "completed_phase": None, "attempt": value.get("recovery_attempts", 0),
                                         "previous_daemon_status": value.get("previous_daemon_status"),
                                         "scheduler_reused": False, "replanning_reused": False,
                                         "event_reused": False, "failure": deepcopy(value.get("failure"))}
        value = save_mission_daemon_state(value, path)
        try:
            _publish_daemon_event(runtime_config, topic="daemon.recovery_blocked", source=value["daemon_id"],
                                  payload=recovery_event_payload(value, value["last_recovery_result"]),
                                  idempotency_key=f"{value['daemon_id']}:daemon.recovery_blocked:{value.get('loop_iteration', 0)}", now=now)
        except Exception:
            pass
        return value
    value["recovery_attempts"] = int(value.get("recovery_attempts") or 0) + 1
    value["recovery_status"] = "recovering"
    value["last_recovery_at"] = time_text(now)
    value = save_mission_daemon_state(value, path)
    try:
        _publish_daemon_event(runtime_config, topic="daemon.recovery_started", source=value["daemon_id"],
                              payload=recovery_event_payload(value),
                              idempotency_key=f"{value['daemon_id']}:daemon.recovery_started:{value['recovery_attempts']}", now=now)
    except Exception:
        pass
    phase = value.get("iteration_phase")
    value["last_recovery_result"] = {"recovered": True, "reason": "checkpoint_resume",
        "resumed_from_phase": phase, "completed_phase": phase, "attempt": value["recovery_attempts"],
        "previous_daemon_status": value["previous_daemon_status"],
        "scheduler_reused": phase in {"scheduler_completed", "replanning_pending", "replanning_completed", "event_publish_pending", "event_published", "iteration_completed"},
        "replanning_reused": phase in {"replanning_completed", "event_publish_pending", "event_published", "iteration_completed"},
        "event_reused": phase in {"event_published", "iteration_completed"}, "failure": None}
    value["recovery_status"] = "recovered"
    value["daemon_status"] = "running"
    value = save_mission_daemon_state(value, path)
    try:
        _publish_daemon_event(runtime_config, topic="daemon.recovered", source=value["daemon_id"],
                              payload=recovery_event_payload(value, value["last_recovery_result"]),
                              idempotency_key=f"{value['daemon_id']}:daemon.recovered:{value['recovery_attempts']}", now=now)
    except Exception:
        pass
    return value


def run_mission_daemon_iteration(
    *,
    daemon_state_path: Any,
    runtime_config: Mapping[str, Any] | None = None,
    lease_seconds: int = 120,
    mission_max_iterations: int = 10,
    now: Any = None,
) -> dict[str, Any]:
    state = load_mission_daemon_state(
        daemon_state_path
    )

    resume_phase = state.get("iteration_phase")
    resuming = resume_phase not in {"idle", "iteration_completed"}
    if not resuming:
        state["loop_iteration"] = int(state.get("loop_iteration") or 0) + 1

    if state.get("stop_requested"):
        state["daemon_status"] = "stopped"
        state["stopped_at"] = time_text(now)
        state["failure"] = None
        state = save_mission_daemon_state(
            _heartbeat(
                state,
                "stopped",
                now=now,
            ),
            daemon_state_path,
        )
        event = _publish_daemon_event(
            runtime_config,
            topic="daemon.stopped",
            source=state["daemon_id"],
            payload={
                "daemon_id": state["daemon_id"],
                "daemon_status": state[
                    "daemon_status"
                ],
                "loop_iteration": state[
                    "loop_iteration"
                ],
            },
            idempotency_key=(
                f"{state['daemon_id']}:stopped:"
                f"{state['loop_iteration']}"
            ),
            now=now,
        )
        state["last_event_id"] = (
            event.get("event_id")
            if event
            else state.get("last_event_id")
        )
        return save_mission_daemon_state(
            state,
            daemon_state_path,
        )

    if state.get("pause_requested"):
        state["idle_iterations"] = int(
            state.get("idle_iterations") or 0
        ) + 1
        state = save_mission_daemon_state(
            _heartbeat(
                state,
                "paused",
                now=now,
            ),
            daemon_state_path,
        )
        event = _publish_daemon_event(
            runtime_config,
            topic="daemon.paused",
            source=state["daemon_id"],
            payload={
                "daemon_id": state["daemon_id"],
                "daemon_status": state[
                    "daemon_status"
                ],
                "loop_iteration": state[
                    "loop_iteration"
                ],
            },
            idempotency_key=(
                f"{state['daemon_id']}:paused:"
                f"{state['loop_iteration']}"
            ),
            now=now,
        )
        state["last_event_id"] = (
            event.get("event_id")
            if event
            else state.get("last_event_id")
        )
        return save_mission_daemon_state(
            state,
            daemon_state_path,
        )

    scheduler_reused = resume_phase in {"scheduler_completed", "replanning_pending", "replanning_completed",
                                        "event_publish_pending", "event_published"}
    if not scheduler_reused:
        state = _checkpoint(state, daemon_state_path, "scheduler_pending", now=now)

    try:
        if scheduler_reused:
            checkpoint = _mapping(state.get("iteration_checkpoint"))
            scheduler = {"scheduler_status": checkpoint.get("scheduler_status"),
                         "last_result": deepcopy(checkpoint.get("scheduler_result")),
                         "failure": deepcopy(checkpoint.get("scheduler_failure"))}
        else:
            scheduler = run_mission_scheduler_iteration(
            scheduler_state_path=state[
                "scheduler_state_path"
            ],
            worker_state_path=state[
                "worker_state_path"
            ],
            worker_name=state["worker_name"],
            target_root=state["target_root"],
            workspace_root=state[
                "workspace_root"
            ],
            runtime_config=runtime_config,
            owner=state["owner"],
            lease_seconds=lease_seconds,
            mission_max_iterations=(
                mission_max_iterations
            ),
            now=now,
            )
    except Exception as exc:
        state["failed_iterations"] = int(
            state.get("failed_iterations") or 0
        ) + 1
        state["failure"] = {
            "critical": False,
            "reasons": [
                f"{type(exc).__name__}:{exc}"
            ],
        }
        state["last_scheduler_result"] = {
            "error": f"{type(exc).__name__}:{exc}"
        }
        return save_mission_daemon_state(
            _heartbeat(
                state,
                "failed",
                now=now,
            ),
            daemon_state_path,
        )

    scheduler_status = str(
        scheduler.get("scheduler_status") or ""
    )
    state["last_scheduler_status"] = (
        scheduler_status
    )
    state["last_scheduler_result"] = deepcopy(
        scheduler.get("last_result")
    )
    state["failure"] = deepcopy(
        scheduler.get("failure")
    )
    if not scheduler_reused:
        state["last_scheduler_completed_iteration"] = state["loop_iteration"]
        state = _checkpoint(state, daemon_state_path, "scheduler_completed", now=now,
                            scheduler_status=scheduler_status, scheduler_result=state["last_scheduler_result"],
                            scheduler_failure=state["failure"])

    if scheduler_status in {"blocked", "failed"}:
        state["blocked_iterations"] = int(
            state.get("blocked_iterations") or 0
        ) + 1
        daemon_status = (
            "failed"
            if scheduler_status == "failed"
            else "blocked"
        )
    elif scheduler_status == "idle":
        state["idle_iterations"] = int(
            state.get("idle_iterations") or 0
        ) + 1
        daemon_status = "idle"
    elif scheduler_status == "paused":
        state["idle_iterations"] = int(
            state.get("idle_iterations") or 0
        ) + 1
        daemon_status = "paused"
    elif scheduler_status == "stopped":
        daemon_status = "stopped"
        state["stopped_at"] = time_text(now)
    else:
        state["successful_iterations"] = int(
            state.get("successful_iterations") or 0
        ) + 1
        state["idle_iterations"] = 0
        daemon_status = "running"

    replanning_reused = resume_phase in {"replanning_completed", "event_publish_pending", "event_published"}
    state = _checkpoint(state, daemon_state_path, "replanning_pending", now=now,
                        daemon_status_after_scheduler=daemon_status)
    try:
        if replanning_reused:
            replanning_result = deepcopy(_mapping(state.get("iteration_checkpoint")).get("replanning_result"))
        else:
            state, replanning_result = (
            _run_replanning_iteration(
                state,
                runtime_config,
                now=now,
            )
            )
    except Exception as exc:
        state["replanning_failures"] = int(
            state.get("replanning_failures") or 0
        ) + 1
        state["last_replanning_status"] = "failed"
        state["last_replanning_result"] = {
            "error": f"{type(exc).__name__}:{exc}"
        }
        state["failure"] = {
            "critical": False,
            "reasons": [
                f"replanning_engine_error:"
                f"{type(exc).__name__}:{exc}"
            ],
        }
        daemon_status = "blocked"
        replanning_result = None

    if not replanning_reused:
        state["last_replanning_completed_iteration"] = state["loop_iteration"]
    state = _checkpoint(state, daemon_state_path, "replanning_completed", now=now,
                        replanning_status=state.get("last_replanning_status"),
                        replanning_result=state.get("last_replanning_result"),
                        daemon_status_after_replanning=daemon_status)

    state = save_mission_daemon_state(
        _heartbeat(
            state,
            daemon_status,
            now=now,
        ),
        daemon_state_path,
    )

    topic = {
        "running": "daemon.heartbeat",
        "idle": "daemon.idle",
        "paused": "daemon.paused",
        "blocked": "daemon.blocked",
        "failed": "daemon.failed",
        "stopped": "daemon.stopped",
    }.get(daemon_status, "daemon.heartbeat")

    state = _checkpoint(state, daemon_state_path, "event_publish_pending", now=now,
                        event_topic=topic, event_payload={"daemon_id": state["daemon_id"],
                        "daemon_status": daemon_status, "loop_iteration": state["loop_iteration"]},
                        event_idempotency_key=f"{state['daemon_id']}:{topic}:{state['loop_iteration']}")

    event = _publish_daemon_event(
        runtime_config,
        topic=topic,
        source=state["daemon_id"],
        payload={
            "daemon_id": state["daemon_id"],
            "daemon_status": daemon_status,
            "loop_iteration": state["loop_iteration"],
            "last_scheduler_status": state.get(
                "last_scheduler_status"
            ),
            "last_scheduler_result": deepcopy(
                state.get("last_scheduler_result")
            ),
            "last_replanning_status": state.get(
                "last_replanning_status"
            ),
            "last_replanning_result": deepcopy(
                state.get("last_replanning_result")
            ),
            "failure": deepcopy(state.get("failure")),
        },
        idempotency_key=(
            f"{state['daemon_id']}:{topic}:"
            f"{state['loop_iteration']}"
        ),
        now=now,
    )
    state["last_event_id"] = (
        event.get("event_id")
        if event
        else state.get("last_event_id")
    )
    state["last_published_event_iteration"] = state["loop_iteration"]
    state["last_published_event_topic"] = topic
    state["last_published_event_id"] = state.get("last_event_id")
    state = _checkpoint(state, daemon_state_path, "event_published", now=now,
                        published_event_id=state.get("last_event_id"))
    state["last_completed_loop_iteration"] = state["loop_iteration"]
    state = _checkpoint(state, daemon_state_path, "iteration_completed", now=now)
    return save_mission_daemon_state(
        state,
        daemon_state_path,
    )


def run_mission_daemon(
    *,
    daemon_state_path: Any,
    runtime_config: Mapping[str, Any] | None = None,
    poll_interval_seconds: float = 1.0,
    lease_seconds: int = 120,
    mission_max_iterations: int = 10,
    max_iterations: int | None = None,
    idle_exit_after: int | None = None,
    now_provider: Callable[[], Any] | None = None,
    sleep_provider: Callable[[float], None] | None = None,
    stop_signal: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    interval = float(poll_interval_seconds)
    if not MIN_POLL_INTERVAL <= interval <= MAX_POLL_INTERVAL:
        raise ValueError(
            "invalid_mission_daemon_poll_interval"
        )

    if (
        max_iterations is not None
        and (
            isinstance(max_iterations, bool)
            or max_iterations < 1
        )
    ):
        raise ValueError(
            "invalid_mission_daemon_max_iterations"
        )

    if (
        idle_exit_after is not None
        and (
            isinstance(idle_exit_after, bool)
            or idle_exit_after < 1
        )
    ):
        raise ValueError(
            "invalid_mission_daemon_idle_exit_after"
        )

    clock = now_provider or (
        lambda: datetime.now(timezone.utc)
    )
    sleeper = sleep_provider or time.sleep

    state = load_mission_daemon_state(
        daemon_state_path
    )
    state = _recover_mission_daemon(state, daemon_state_path, runtime_config, now=clock())
    if state.get("recovery_status") == "blocked":
        return state
    state["started_at"] = (
        state.get("started_at")
        or time_text(clock())
    )
    state["stopped_at"] = None
    state = save_mission_daemon_state(
        _heartbeat(
            state,
            "starting",
            now=clock(),
        ),
        daemon_state_path,
    )

    iterations = 0

    while True:
        if stop_signal and stop_signal():
            state = load_mission_daemon_state(
                daemon_state_path
            )
            state = request_mission_daemon_action(
                state,
                "stop",
                now=clock(),
            )
            save_mission_daemon_state(
                state,
                daemon_state_path,
            )

        state = run_mission_daemon_iteration(
            daemon_state_path=daemon_state_path,
            runtime_config=runtime_config,
            lease_seconds=lease_seconds,
            mission_max_iterations=(
                mission_max_iterations
            ),
            now=clock(),
        )
        iterations += 1

        if state["daemon_status"] in {
            "stopped",
            "failed",
        }:
            break

        if (
            max_iterations is not None
            and iterations >= max_iterations
        ):
            state = request_mission_daemon_action(
                state,
                "stop",
                now=clock(),
            )
            save_mission_daemon_state(
                state,
                daemon_state_path,
            )

        if (
            idle_exit_after is not None
            and int(state.get("idle_iterations") or 0)
            >= idle_exit_after
        ):
            state = request_mission_daemon_action(
                state,
                "stop",
                now=clock(),
            )
            save_mission_daemon_state(
                state,
                daemon_state_path,
            )

        if state.get("stop_requested"):
            state = run_mission_daemon_iteration(
                daemon_state_path=daemon_state_path,
                runtime_config=runtime_config,
                lease_seconds=lease_seconds,
                mission_max_iterations=(
                    mission_max_iterations
                ),
                now=clock(),
            )
            break

        sleeper(interval)

    return state


def mission_daemon_health(
    state: Mapping[str, Any],
    *,
    now: Any = None,
) -> dict[str, Any]:
    value = _mapping(state)
    reasons = validate_mission_daemon_state(value)

    current = parse_time(
        now or datetime.now(timezone.utc)
    )
    try:
        heartbeat = parse_time(
            value.get("last_heartbeat_at")
        )
        fresh = (
            current - heartbeat
        ).total_seconds() <= HEARTBEAT_FRESH_SECONDS
    except (TypeError, ValueError):
        fresh = False

    if not fresh:
        reasons.append("stale_mission_daemon_heartbeat")

    critical = (
        value.get("daemon_status") == "failed"
        or _mapping(value.get("failure")).get(
            "critical"
        )
        is True
    )
    if critical:
        reasons.append(
            "mission_daemon_critical_failure"
        )

    decision = recovery_decision(value)
    if value.get("recovery_status") in {"blocked", "failed"}:
        reasons.append(f"mission_daemon_recovery_{value.get('recovery_status')}")
    if decision["recovery_attempts_exhausted"]:
        reasons.append("mission_daemon_recovery_attempts_exhausted")
    if not decision["checkpoint_valid"]:
        reasons.append("invalid_mission_daemon_checkpoint")

    return {
        "healthy": (
            not reasons
            and value.get("daemon_status")
            not in {"blocked", "failed"}
        ),
        "daemon_status": value.get(
            "daemon_status"
        ),
        "heartbeat_fresh": fresh,
        "critical_failure": critical,
        "loop_iteration": int(
            value.get("loop_iteration") or 0
        ),
        "last_scheduler_status": value.get(
            "last_scheduler_status"
        ),
        "recovery_status": value.get("recovery_status"),
        "recovery_attempts": int(value.get("recovery_attempts") or 0),
        "recovery_failures": int(value.get("recovery_failures") or 0),
        "iteration_phase": value.get("iteration_phase"),
        "last_completed_loop_iteration": int(value.get("last_completed_loop_iteration") or 0),
        "last_scheduler_completed_iteration": int(value.get("last_scheduler_completed_iteration") or 0),
        "last_replanning_completed_iteration": int(value.get("last_replanning_completed_iteration") or 0),
        "last_published_event_iteration": int(value.get("last_published_event_iteration") or 0),
        "recoverable": decision["recoverable"],
        "recovery_attempts_exhausted": decision["recovery_attempts_exhausted"],
        "checkpoint_valid": decision["checkpoint_valid"],
        "reasons": reasons,
    }


__all__ = [
    "CONTRACT",
    "HEARTBEAT_FRESH_SECONDS",
    "MAX_POLL_INTERVAL",
    "MIN_POLL_INTERVAL",
    "VALID_STATUSES",
    "create_mission_daemon_state",
    "load_mission_daemon_state",
    "mission_daemon_health",
    "request_mission_daemon_action",
    "run_mission_daemon",
    "run_mission_daemon_iteration",
    "save_mission_daemon_state",
    "seal_mission_daemon_state",
    "validate_mission_daemon_state",
]
