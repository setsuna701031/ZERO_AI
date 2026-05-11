from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional

from core.planning.planner_contract_adapter import adapt_planner_result


@dataclass(frozen=True)
class PlannerRuntimeEntryResult:
    ok: bool
    payload: Dict[str, Any]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    invoked: bool = False
    invocation_error: Optional[str] = None


def run_planner_runtime_entry(
    planner: Any,
    request: Any,
    *,
    method_name: str = "plan",
) -> PlannerRuntimeEntryResult:
    try:
        raw_result = _invoke_planner(planner, request, method_name=method_name)
    except Exception as exc:
        error = f"planner_invocation_failed:{type(exc).__name__}:{exc}"
        adapted = adapt_planner_result(
            {
                "action": "noop",
                "reason": error,
                "metadata": {"invoked": False},
            }
        )
        payload = dict(adapted.payload)
        payload["runtime_entry_ok"] = False
        payload["runtime_entry_invoked"] = False
        payload["runtime_entry_error"] = error

        return PlannerRuntimeEntryResult(
            ok=False,
            payload=payload,
            errors=[error],
            warnings=list(adapted.warnings),
            invoked=False,
            invocation_error=error,
        )

    adapted = adapt_planner_result(raw_result)
    payload = dict(adapted.payload)
    payload["runtime_entry_ok"] = adapted.ok
    payload["runtime_entry_invoked"] = True
    payload["runtime_entry_error"] = None

    return PlannerRuntimeEntryResult(
        ok=adapted.ok,
        payload=payload,
        errors=list(adapted.errors),
        warnings=list(adapted.warnings),
        invoked=True,
        invocation_error=None,
    )


def export_planner_runtime_payload(
    planner: Any,
    request: Any,
    *,
    method_name: str = "plan",
) -> Dict[str, Any]:
    return run_planner_runtime_entry(
        planner,
        request,
        method_name=method_name,
    ).payload


def _invoke_planner(planner: Any, request: Any, *, method_name: str) -> Any:
    if callable(planner):
        return planner(request)

    if planner is None:
        raise TypeError("planner is None")

    method = getattr(planner, method_name, None)
    if not callable(method):
        raise AttributeError(f"planner method not callable: {method_name}")

    return method(request)