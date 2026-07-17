from __future__ import annotations

import copy
from typing import Any, Dict


def mark_agent_loop_route(response: Dict[str, Any], route_name: str) -> Dict[str, Any]:
    """Add stable AgentLoop route metadata without owning route transitions."""

    if not isinstance(response, dict):
        return {
            "ok": False,
            "mode": "agent_loop_invalid_response",
            "context": {},
            "route": None,
            "plan": None,
            "execution": None,
            "final_answer": "",
            "error": "agent loop produced non-dict response",
            "raw_response": copy.deepcopy(response),
            "agent_loop_runtime_route": str(route_name or "unknown"),
            "agent_loop_route_marker": True,
        }
    marker = str(route_name or response.get("agent_loop_runtime_route") or response.get("mode") or "unknown")
    response["agent_loop_runtime_route"] = marker
    response["agent_loop_route_marker"] = True
    response.setdefault("agent_loop_main_path", "AgentLoop.run -> _try_agent_loop_pre_routes -> _run_default_agent_route")
    return response
