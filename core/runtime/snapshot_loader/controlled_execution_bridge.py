from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional

from core.runtime.snapshot_loader.execution_routing import (
    build_runtime_routing_summary,
    route_mutation_runtime,
    route_patch_apply,
    route_readonly_execution,
    route_unrestricted_shell,
)


RuntimeHandler = Callable[[Mapping[str, Any]], Any]


_ROUTE_TABLE = {
    "readonly_execution": route_readonly_execution,
    "mutation_runtime": route_mutation_runtime,
    "patch_apply": route_patch_apply,
    "unrestricted_shell": route_unrestricted_shell,
}


def build_bridge_rejection(
    action: str,
    decision: Mapping[str, Any],
    payload: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "ok": False,
        "status": "blocked",
        "action": action,
        "reason": decision.get("reason", "blocked_by_runtime_governance"),
        "decision": dict(decision),
        "payload": dict(payload or {}),
    }


def build_bridge_result(
    action: str,
    decision: Mapping[str, Any],
    result: Any,
) -> Dict[str, Any]:
    return {
        "ok": True,
        "status": "executed",
        "action": action,
        "decision": dict(decision),
        "result": result,
    }


def route_controlled_execution(
    action: str,
    payload: Optional[Mapping[str, Any]] = None,
    handlers: Optional[Mapping[str, RuntimeHandler]] = None,
) -> Dict[str, Any]:
    if not isinstance(action, str) or not action.strip():
        raise ValueError("action must be a non-empty string")

    normalized_action = action.strip()
    route_func = _ROUTE_TABLE.get(normalized_action)

    if route_func is None:
        decision = {
            "action": normalized_action,
            "allowed": False,
            "reason": "unknown_runtime_action",
        }
        return build_bridge_rejection(
            action=normalized_action,
            decision=decision,
            payload=payload,
        )

    decision = route_func()

    if not decision.get("allowed", False):
        return build_bridge_rejection(
            action=normalized_action,
            decision=decision,
            payload=payload,
        )

    handler_table = handlers or {}
    handler = handler_table.get(normalized_action)

    if handler is None:
        return {
            "ok": True,
            "status": "allowed_no_handler",
            "action": normalized_action,
            "decision": dict(decision),
            "payload": dict(payload or {}),
        }

    result = handler(payload or {})
    return build_bridge_result(
        action=normalized_action,
        decision=decision,
        result=result,
    )


def build_controlled_execution_bridge_summary() -> Dict[str, Any]:
    routing_summary = build_runtime_routing_summary()

    return {
        "bridge": "controlled_execution_bridge",
        "routing": routing_summary,
        "allowed_actions": list(routing_summary.get("allowed_actions", [])),
        "blocked_actions": list(routing_summary.get("blocked_actions", [])),
        "known_actions": sorted(_ROUTE_TABLE.keys()),
    }