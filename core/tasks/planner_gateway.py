from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.planning.planner_runtime_entry import run_planner_runtime_entry


@dataclass(frozen=True)
class PlannerGatewayResult:
    ok: bool
    payload: Dict[str, Any]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    gateway_error: Optional[str] = None


def call_planner_gateway(
    planner: Any,
    request: Any,
    *,
    method_name: str = "plan",
) -> PlannerGatewayResult:
    runtime_result = run_planner_runtime_entry(
        planner,
        request,
        method_name=method_name,
    )

    payload = dict(runtime_result.payload)
    payload["planner_gateway_ok"] = runtime_result.ok
    payload["planner_gateway_errors"] = list(runtime_result.errors)
    payload["planner_gateway_warnings"] = list(runtime_result.warnings)

    gateway_error = runtime_result.invocation_error
    payload["planner_gateway_error"] = gateway_error

    return PlannerGatewayResult(
        ok=runtime_result.ok,
        payload=payload,
        errors=list(runtime_result.errors),
        warnings=list(runtime_result.warnings),
        gateway_error=gateway_error,
    )


def export_scheduler_planner_payload(
    planner: Any,
    request: Any,
    *,
    method_name: str = "plan",
) -> Dict[str, Any]:
    return call_planner_gateway(
        planner,
        request,
        method_name=method_name,
    ).payload


def build_noop_planner_payload(
    *,
    reason: str,
    goal: str = "",
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "contract_version": "planner_contract.v1",
        "action": "noop",
        "raw_action": "noop",
        "goal": goal,
        "target_path": None,
        "content": "",
        "command": "",
        "reason": reason,
        "metadata": {},
        "is_valid": True,
        "contract_errors": [],
        "contract_warnings": [],
        "adapter_ok": True,
        "adapter_errors": [],
        "adapter_warnings": [],
        "runtime_entry_ok": True,
        "runtime_entry_invoked": False,
        "runtime_entry_error": None,
        "planner_gateway_ok": True,
        "planner_gateway_errors": [],
        "planner_gateway_warnings": [],
        "planner_gateway_error": None,
    }
    return payload