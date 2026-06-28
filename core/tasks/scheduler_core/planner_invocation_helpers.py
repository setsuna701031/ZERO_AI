from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List


def _planner_candidate_calls(
    context: Dict[str, Any],
    user_input: str,
    route: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return [
        {"context": context, "user_input": user_input, "route": route},
        {"context": context, "user_input": user_input},
        {"context": context},
        {"user_input": user_input, "route": route},
        {"user_input": user_input},
    ]


def _iter_planner_methods(planner: Any) -> Iterable[Callable[..., Any]]:
    for method_name in ("plan", "run", "__call__"):
        method = getattr(planner, method_name, None)
        if callable(method):
            yield method


def _invoke_planner_method(
    method: Callable[..., Any],
    candidate_calls: Iterable[Dict[str, Any]],
    user_input: str,
    gateway_adapter: Callable[[Any], Any],
) -> Any:
    for kwargs in candidate_calls:
        try:
            raw_plan = method(**kwargs)
            return gateway_adapter(raw_plan)
        except TypeError:
            continue
        except Exception:
            return None

    try:
        raw_plan = method(user_input)
        return gateway_adapter(raw_plan)
    except Exception:
        return None
