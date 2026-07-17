from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_goal_execution_registry import (
    create_goal_execution_registry,
    load_goal_execution_registry,
    pending_goal_execution_requests,
    register_goal_execution_request,
    save_goal_execution_registry,
)
from core.runtime.runtime_operator_session import (
    fingerprint,
    load_runtime_session,
    time_text,
)

CONTRACT = "zero.runtime.mission_execution_registry_bridge.v1"


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _default_registry_path(mission: Mapping[str, Any]) -> Path:
    mission_path = str(mission.get("mission_path") or "").strip()
    if not mission_path:
        raise ValueError("mission_path_required")

    source = Path(mission_path)
    return source.with_name(
        f"{source.stem}.goal-execution-registry.json"
    )


def _registry_id(mission: Mapping[str, Any]) -> str:
    mission_id = str(mission.get("mission_id") or "").strip()
    if not mission_id:
        raise ValueError("mission_id_required")
    return f"goal-execution-registry-{mission_id}"


def _load_or_create_registry(
    mission: Mapping[str, Any],
    *,
    registry_path: Path,
    now: Any,
) -> dict[str, Any]:
    if registry_path.exists():
        registry = load_goal_execution_registry(registry_path)
        expected = _registry_id(mission)
        if registry.get("registry_id") != expected:
            raise ValueError("registry_mission_identity_mismatch")
        return registry

    return create_goal_execution_registry(
        registry_id=_registry_id(mission),
        now=now,
    )


def _artifact_root_for_session(
    *,
    mission: Mapping[str, Any],
    session_id: str,
    runtime_config: Mapping[str, Any],
) -> Path:
    config = _mapping(runtime_config)

    configured = (
        config.get("goal_execution_artifact_root")
        or config.get("executor_artifact_root")
        or config.get("artifact_root")
    )

    if configured:
        root = Path(configured)
    else:
        mission_path = str(
            mission.get("mission_path") or ""
        ).strip()
        if not mission_path:
            raise ValueError(
                "goal_execution_artifact_root_required"
            )
        source = Path(mission_path)
        root = source.parent / (
            f"{source.stem}.goal-execution-artifacts"
        )

    return root / session_id


def _goal_for_session(
    mission: Mapping[str, Any],
    *,
    goal_id: str,
) -> dict[str, Any]:
    goals = _mapping(mission.get("goals"))
    goal = _mapping(goals.get(goal_id))

    if not goal:
        raise ValueError("goal_not_found_for_session")

    if not goal.get("goal_id"):
        goal["goal_id"] = goal_id

    if not goal.get("mission_id"):
        goal["mission_id"] = mission.get("mission_id")

    return goal


def sync_mission_execution_registry(
    mission: Mapping[str, Any],
    *,
    target_root: Any,
    workspace_root: Any,
    runtime_config: Mapping[str, Any] | None = None,
    registry_path: Any = None,
    now: Any = None,
) -> dict[str, Any]:
    """
    Synchronize candidate-ready Mission sessions into a persistent Goal
    Execution Registry.

    This bridge does not invoke the Worker, Executor, approval gates,
    Transaction Runtime, or workspace mutation. It only registers immutable
    Goal Execution Requests and returns the runtime_config overlay expected by
    the existing Worker service.

    Root arguments are intentionally not used while loading the session.
    This bridge only inspects and registers an already sealed session; runtime
    root enforcement remains at the Worker / Executor execution boundary.
    """
    value = _mapping(mission)
    config = _mapping(runtime_config)

    mission_id = str(value.get("mission_id") or "").strip()
    if not mission_id:
        raise ValueError("mission_id_required")

    destination = (
        Path(registry_path)
        if registry_path is not None
        else _default_registry_path(value)
    )

    registry = _load_or_create_registry(
        value,
        registry_path=destination,
        now=now,
    )

    registered_session_ids: list[str] = []
    skipped_session_ids: list[str] = []
    blocked_sessions: list[dict[str, Any]] = []

    session_references = _mapping(
        value.get("session_references")
    )

    for goal_id in value.get("goal_order") or []:
        references = session_references.get(goal_id) or []
        if not isinstance(references, list) or not references:
            continue

        reference = _mapping(references[-1])
        if reference.get("archived") is True:
            continue

        session_id = str(
            reference.get("session_id") or ""
        ).strip()
        session_path = str(
            reference.get("session_path") or ""
        ).strip()

        if not session_id or not session_path:
            blocked_sessions.append(
                {
                    "goal_id": goal_id,
                    "session_id": session_id,
                    "reason": "invalid_session_reference",
                }
            )
            continue

        try:
            session = load_runtime_session(
                session_path,
                now=now,
            )
        except (OSError, TypeError, ValueError) as exc:
            blocked_sessions.append(
                {
                    "goal_id": goal_id,
                    "session_id": session_id,
                    "reason": f"{type(exc).__name__}:{exc}",
                }
            )
            continue

        if session.get("session_id") != session_id:
            blocked_sessions.append(
                {
                    "goal_id": goal_id,
                    "session_id": session_id,
                    "reason": "session_identity_mismatch",
                }
            )
            continue

        if session.get("session_status") != (
            "waiting_for_candidate_bundle"
        ):
            skipped_session_ids.append(session_id)
            continue

        try:
            goal = _goal_for_session(
                value,
                goal_id=goal_id,
            )
            artifact_root = _artifact_root_for_session(
                mission=value,
                session_id=session_id,
                runtime_config=config,
            )
            registry = register_goal_execution_request(
                registry,
                mission=value,
                goal=goal,
                session=session,
                artifact_root=artifact_root,
                now=now,
            )
            registered_session_ids.append(session_id)
        except (OSError, TypeError, ValueError) as exc:
            blocked_sessions.append(
                {
                    "goal_id": goal_id,
                    "session_id": session_id,
                    "reason": f"{type(exc).__name__}:{exc}",
                }
            )

    registry = save_goal_execution_registry(
        registry,
        destination,
    )

    requests = pending_goal_execution_requests(registry)
    runtime_config_overlay = deepcopy(config)
    runtime_config_overlay[
        "goal_execution_requests"
    ] = requests
    runtime_config_overlay[
        "goal_execution_registry_path"
    ] = str(destination.resolve(strict=False))
    runtime_config_overlay[
        "goal_execution_registry_fingerprint"
    ] = registry["registry_fingerprint"]

    summary_unsigned = {
        "contract": CONTRACT,
        "mission_id": mission_id,
        "registry_id": registry["registry_id"],
        "registry_path": str(
            destination.resolve(strict=False)
        ),
        "registry_fingerprint": registry[
            "registry_fingerprint"
        ],
        "registered_session_ids": sorted(
            set(registered_session_ids)
        ),
        "skipped_session_ids": sorted(
            set(skipped_session_ids)
        ),
        "blocked_sessions": deepcopy(blocked_sessions),
        "pending_request_session_ids": sorted(requests),
        "pending_request_count": len(requests),
        "runtime_config_overlay": runtime_config_overlay,
        "workspace_mutated": False,
        "worker_invoked": False,
        "executor_invoked": False,
        "transaction_invoked": False,
        "generated_at": time_text(now),
    }
    summary = deepcopy(summary_unsigned)
    summary["bridge_fingerprint"] = fingerprint(
        summary_unsigned
    )
    return summary


__all__ = [
    "CONTRACT",
    "sync_mission_execution_registry",
]
