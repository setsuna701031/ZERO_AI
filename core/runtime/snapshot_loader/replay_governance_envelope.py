from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from core.runtime.snapshot_loader.execution_gateway_integration import (
    execute_gateway_action,
)


def build_replay_governance_event(
    action: str,
    payload: Optional[Mapping[str, Any]] = None,
    replay_id: str = "runtime_replay",
    sequence: int = 0,
    source: str = "runtime_replay",
) -> Dict[str, Any]:
    if not isinstance(action, str) or not action.strip():
        raise ValueError("action must be a non-empty string")
    if not isinstance(sequence, int) or sequence < 0:
        raise ValueError("sequence must be a non-negative integer")

    return {
        "replay_id": replay_id,
        "sequence": sequence,
        "source": source,
        "action": action.strip(),
        "payload": dict(payload or {}),
    }


def evaluate_replay_governance_event(
    event: Mapping[str, Any],
) -> Dict[str, Any]:
    if not isinstance(event, Mapping):
        raise TypeError("event must be a mapping")

    action = event.get("action")
    if not isinstance(action, str) or not action.strip():
        raise ValueError("event.action must be a non-empty string")

    payload = event.get("payload", {})
    if payload is None:
        payload = {}
    if not isinstance(payload, Mapping):
        raise TypeError("event.payload must be a mapping")

    gateway_result = execute_gateway_action(
        action=action,
        payload=payload,
        source=str(event.get("source", "runtime_replay")),
    )

    bridge_result = gateway_result.get("bridge_result", {})
    decision = bridge_result.get("decision", {})

    return {
        "ok": gateway_result.get("ok", False),
        "status": gateway_result.get("status"),
        "replay_id": event.get("replay_id", "runtime_replay"),
        "sequence": event.get("sequence", 0),
        "source": event.get("source", "runtime_replay"),
        "action": action.strip(),
        "governance": {
            "allowed": bool(decision.get("allowed", False)),
            "reason": decision.get("reason"),
            "decision": dict(decision),
        },
        "gateway_result": gateway_result,
    }


def build_replay_governance_summary(
    events: list[Mapping[str, Any]],
) -> Dict[str, Any]:
    if not isinstance(events, list):
        raise TypeError("events must be a list")

    evaluations = [
        evaluate_replay_governance_event(event)
        for event in events
    ]

    allowed_actions = [
        item["action"]
        for item in evaluations
        if item["governance"]["allowed"] is True
    ]

    blocked_actions = [
        item["action"]
        for item in evaluations
        if item["governance"]["allowed"] is False
    ]

    return {
        "replay_governance": "snapshot_loader_replay_governance_envelope",
        "event_count": len(evaluations),
        "allowed_actions": allowed_actions,
        "blocked_actions": blocked_actions,
        "events": evaluations,
    }