from __future__ import annotations

import traceback
from typing import Any, Dict, Optional


def _component_contract_error(
    *,
    component: str,
    method: str,
    source: str,
    required_contract: str,
    error: str,
    include_traceback: bool = False,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "ok": False,
        "component": component,
        "component_method": method,
        "component_source": source,
        "component_route": f"{source}.{component}",
        "component_contract_mismatch": True,
        "legacy_adapter": False,
        "error": error,
        "required_contract": required_contract,
    }
    if component in {"planner", "llm_planner"}:
        payload["_planner_error"] = True
    if include_traceback:
        payload["traceback"] = traceback.format_exc()
    return payload


def _component_runtime_error(
    *,
    component: str,
    method: str,
    source: str,
    error: str,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "ok": False,
        "component": component,
        "component_method": method,
        "component_source": source,
        "component_route": f"{source}.{component}",
        "error": error,
        "traceback": traceback.format_exc(),
    }
    if component in {"planner", "llm_planner"}:
        payload["_planner_error"] = True
    return payload


def _required_method(obj: Any, method_name: str) -> Any:
    fn = getattr(obj, method_name, None)
    return fn if callable(fn) else None


def call_router(router: Any, context: Dict[str, Any], user_input: str) -> Any:
    if not router:
        return None

    method_name = "route"
    router_fn = _required_method(router, method_name)
    source = "agent_loop"
    required_contract = "route(context=..., user_input=..., source=...)"
    if router_fn is None:
        return _component_contract_error(
            component="router",
            method=method_name,
            source=source,
            required_contract=required_contract,
            error="router has no callable route method",
        )

    try:
        return router_fn(context=context, user_input=user_input, source=source)
    except Exception as exc:
        if isinstance(exc, TypeError):
            return _component_contract_error(
                component="router",
                method=method_name,
                source=source,
                required_contract=required_contract,
                error=f"router contract mismatch: {type(exc).__name__}: {exc}",
            )
        return _component_runtime_error(
            component="router",
            method=method_name,
            source=source,
            error=f"router invocation failed: {type(exc).__name__}: {exc}",
        )


def call_planner(
    planner: Any,
    context: Dict[str, Any],
    user_input: str,
    route: Any,
) -> Any:
    return _call_planner_component(
        component_name="planner",
        planner=planner,
        context=context,
        user_input=user_input,
        route=route,
    )


def call_llm_planner(
    llm_planner: Any,
    context: Dict[str, Any],
    user_input: str,
    route: Any,
) -> Any:
    return _call_planner_component(
        component_name="llm_planner",
        planner=llm_planner,
        context=context,
        user_input=user_input,
        route=route,
    )


def _call_planner_component(
    *,
    component_name: str,
    planner: Any,
    context: Dict[str, Any],
    user_input: str,
    route: Any,
) -> Any:
    if not planner:
        return None

    method_name = "plan"
    planner_fn = _required_method(planner, method_name)
    source = "agent_loop"
    required_contract = "plan(context=..., user_input=..., route=..., source=...)"
    if planner_fn is None:
        return _component_contract_error(
            component=component_name,
            method=method_name,
            source=source,
            required_contract=required_contract,
            error=f"{component_name} has no callable plan method",
        )

    try:
        return planner_fn(
            context=context,
            user_input=user_input,
            route=route,
            source=source,
        )
    except Exception as exc:
        if isinstance(exc, TypeError):
            return _component_contract_error(
                component=component_name,
                method=method_name,
                source=source,
                required_contract=required_contract,
                error=f"{component_name} contract mismatch: {type(exc).__name__}: {exc}",
            )
        return _component_runtime_error(
            component=component_name,
            method=method_name,
            source=source,
            error=f"{component_name} invocation failed: {type(exc).__name__}: {exc}",
        )


def call_step_executor(
    step_executor: Any,
    step: Any,
    context: Dict[str, Any],
    user_input: str,
    route: Any,
    previous_result: Any = None,
    step_index: Optional[int] = None,
    step_count: Optional[int] = None,
) -> Any:
    if not step_executor:
        return None

    method_name = "execute"
    executor_fn = _required_method(step_executor, method_name)
    source = "agent_loop"
    required_contract = (
        "execute(step=..., context=..., user_input=..., route=..., "
        "previous_result=..., step_index=..., step_count=..., source=...)"
    )
    if executor_fn is None:
        return _component_contract_error(
            component="step_executor",
            method=method_name,
            source=source,
            required_contract=required_contract,
            error="step_executor has no callable execute method",
        )

    try:
        return executor_fn(
            step=step,
            context=context,
            user_input=user_input,
            route=route,
            previous_result=previous_result,
            step_index=step_index,
            step_count=step_count,
            source=source,
        )
    except Exception as exc:
        if isinstance(exc, TypeError):
            return _component_contract_error(
                component="step_executor",
                method=method_name,
                source=source,
                required_contract=required_contract,
                error=f"step_executor contract mismatch: {type(exc).__name__}: {exc}",
            )
        return _component_runtime_error(
            component="step_executor",
            method=method_name,
            source=source,
            error=f"step_executor invocation failed: {type(exc).__name__}: {exc}",
        )


def run_verifier(verifier: Any, execution_result: Any) -> Any:
    if not verifier:
        return execution_result

    method_name = "verify"
    verify_fn = _required_method(verifier, method_name)
    source = "agent_loop"
    required_contract = "verify(result=..., source=...)"
    if verify_fn is None:
        return _component_contract_error(
            component="verifier",
            method=method_name,
            source=source,
            required_contract=required_contract,
            error="verifier has no callable verify method",
        )

    try:
        return verify_fn(result=execution_result, source=source)
    except Exception as exc:
        if isinstance(exc, TypeError):
            return _component_contract_error(
                component="verifier",
                method=method_name,
                source=source,
                required_contract=required_contract,
                error=f"verifier contract mismatch: {type(exc).__name__}: {exc}",
            )
        return _component_runtime_error(
            component="verifier",
            method=method_name,
            source=source,
            error=f"verifier invocation failed: {type(exc).__name__}: {exc}",
        )


def run_safety_guard(safety_guard: Any, execution_result: Any) -> Any:
    if not safety_guard:
        return execution_result

    method_name = "check"
    guard_fn = _required_method(safety_guard, method_name)
    source = "agent_loop"
    required_contract = "check(result=..., source=...)"
    if guard_fn is None:
        return _component_contract_error(
            component="safety_guard",
            method=method_name,
            source=source,
            required_contract=required_contract,
            error="safety_guard has no callable check method",
        )

    try:
        return guard_fn(result=execution_result, source=source)
    except Exception as exc:
        if isinstance(exc, TypeError):
            return _component_contract_error(
                component="safety_guard",
                method=method_name,
                source=source,
                required_contract=required_contract,
                error=f"safety_guard contract mismatch: {type(exc).__name__}: {exc}",
            )
        return _component_runtime_error(
            component="safety_guard",
            method=method_name,
            source=source,
            error=f"safety_guard invocation failed: {type(exc).__name__}: {exc}",
        )
