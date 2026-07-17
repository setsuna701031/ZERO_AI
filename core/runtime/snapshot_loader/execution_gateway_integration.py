from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional

from core.runtime.snapshot_loader.controlled_execution_bridge import (
    build_controlled_execution_bridge_summary,
    route_controlled_execution,
)


RuntimeHandler = Callable[[Mapping[str, Any]], Any]


def build_gateway_request(
    action: str,
    payload: Optional[Mapping[str, Any]] = None,
    source: str = "runtime_gateway",
) -> Dict[str, Any]:
    if not isinstance(action, str) or not action.strip():
        raise ValueError("action must be a non-empty string")

    return {
        "source": source,
        "action": action.strip(),
        "payload": dict(payload or {}),
    }


def execute_gateway_request(
    request: Mapping[str, Any],
    handlers: Optional[Mapping[str, RuntimeHandler]] = None,
) -> Dict[str, Any]:
    if not isinstance(request, Mapping):
        raise TypeError("request must be a mapping")

    action = request.get("action")
    if not isinstance(action, str) or not action.strip():
        raise ValueError("request.action must be a non-empty string")

    payload = request.get("payload", {})
    if payload is None:
        payload = {}
    if not isinstance(payload, Mapping):
        raise TypeError("request.payload must be a mapping")

    bridge_result = route_controlled_execution(
        action=action,
        payload=payload,
        handlers=handlers,
    )

    return {
        "ok": bridge_result.get("ok", False),
        "status": bridge_result.get("status"),
        "source": request.get("source", "runtime_gateway"),
        "action": action.strip(),
        "gateway": "snapshot_loader_execution_gateway",
        "bridge_result": bridge_result,
    }


def execute_gateway_action(
    action: str,
    payload: Optional[Mapping[str, Any]] = None,
    handlers: Optional[Mapping[str, RuntimeHandler]] = None,
    source: str = "runtime_gateway",
) -> Dict[str, Any]:
    request = build_gateway_request(
        action=action,
        payload=payload,
        source=source,
    )
    return execute_gateway_request(
        request=request,
        handlers=handlers,
    )


def build_execution_gateway_integration_summary() -> Dict[str, Any]:
    bridge_summary = build_controlled_execution_bridge_summary()

    return {
        "gateway": "snapshot_loader_execution_gateway",
        "bridge": bridge_summary.get("bridge"),
        "allowed_actions": list(bridge_summary.get("allowed_actions", [])),
        "blocked_actions": list(bridge_summary.get("blocked_actions", [])),
        "known_actions": list(bridge_summary.get("known_actions", [])),
    }