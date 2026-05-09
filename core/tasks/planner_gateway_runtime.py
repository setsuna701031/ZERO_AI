from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from core.tasks.planner_gateway import (
    build_noop_planner_payload,
    call_planner_gateway,
)


@dataclass(frozen=True)
class PlannerGatewayRuntimeResult:
    ok: bool
    payload: Dict[str, Any]
    legacy_payload: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    used_gateway: bool = False
    used_legacy_fallback: bool = False
    runtime_error: Optional[str] = None


def run_scheduler_planner_gateway(
    planner: Any,
    request: Any,
    *,
    method_name: str = "plan",
    legacy_payload: Optional[Mapping[str, Any]] = None,
    allow_legacy_fallback: bool = True,
) -> PlannerGatewayRuntimeResult:
    gateway_result = call_planner_gateway(
        planner,
        request,
        method_name=method_name,
    )

    if gateway_result.ok:
        payload = _scheduler_safe_payload(gateway_result.payload)
        payload["scheduler_planner_gateway_used"] = True
        payload["scheduler_planner_legacy_fallback_used"] = False
        payload["scheduler_planner_runtime_ok"] = True
        payload["scheduler_planner_runtime_error"] = None

        return PlannerGatewayRuntimeResult(
            ok=True,
            payload=payload,
            legacy_payload=dict(legacy_payload or {}),
            errors=[],
            warnings=list(gateway_result.warnings),
            used_gateway=True,
            used_legacy_fallback=False,
            runtime_error=None,
        )

    if allow_legacy_fallback and isinstance(legacy_payload, Mapping):
        fallback_payload = _scheduler_safe_payload(dict(legacy_payload))
        fallback_payload["scheduler_planner_gateway_used"] = False
        fallback_payload["scheduler_planner_legacy_fallback_used"] = True
        fallback_payload["scheduler_planner_runtime_ok"] = True
        fallback_payload["scheduler_planner_runtime_error"] = None
        fallback_payload["planner_gateway_errors"] = list(gateway_result.errors)
        fallback_payload["planner_gateway_warnings"] = list(gateway_result.warnings)

        return PlannerGatewayRuntimeResult(
            ok=True,
            payload=fallback_payload,
            legacy_payload=dict(legacy_payload),
            errors=list(gateway_result.errors),
            warnings=list(gateway_result.warnings),
            used_gateway=False,
            used_legacy_fallback=True,
            runtime_error=None,
        )

    reason = gateway_result.gateway_error or ";".join(gateway_result.errors) or "planner_gateway_failed"
    noop_payload = build_noop_planner_payload(
        reason=reason,
        goal=_extract_goal(request),
    )
    noop_payload["scheduler_planner_gateway_used"] = False
    noop_payload["scheduler_planner_legacy_fallback_used"] = False
    noop_payload["scheduler_planner_runtime_ok"] = False
    noop_payload["scheduler_planner_runtime_error"] = reason
    noop_payload["planner_gateway_errors"] = list(gateway_result.errors)
    noop_payload["planner_gateway_warnings"] = list(gateway_result.warnings)

    return PlannerGatewayRuntimeResult(
        ok=False,
        payload=noop_payload,
        legacy_payload=dict(legacy_payload or {}),
        errors=list(gateway_result.errors),
        warnings=list(gateway_result.warnings),
        used_gateway=False,
        used_legacy_fallback=False,
        runtime_error=reason,
    )


def export_scheduler_runtime_planner_payload(
    planner: Any,
    request: Any,
    *,
    method_name: str = "plan",
    legacy_payload: Optional[Mapping[str, Any]] = None,
    allow_legacy_fallback: bool = True,
) -> Dict[str, Any]:
    return run_scheduler_planner_gateway(
        planner,
        request,
        method_name=method_name,
        legacy_payload=legacy_payload,
        allow_legacy_fallback=allow_legacy_fallback,
    ).payload


def _scheduler_safe_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    safe = dict(payload)

    safe.setdefault("action", "noop")
    safe.setdefault("target_path", None)
    safe.setdefault("content", "")
    safe.setdefault("command", "")
    safe.setdefault("goal", "")
    safe.setdefault("reason", "")
    safe.setdefault("metadata", {})
    safe.setdefault("is_valid", True)
    safe.setdefault("contract_errors", [])
    safe.setdefault("contract_warnings", [])

    return safe


def _extract_goal(request: Any) -> str:
    if not isinstance(request, Mapping):
        return ""

    value = request.get("goal") or request.get("task") or request.get("description")
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, (int, float, bool)):
        return str(value).strip()

    return ""