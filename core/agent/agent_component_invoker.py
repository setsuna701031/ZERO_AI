from __future__ import annotations

import traceback
from typing import Any, Dict, Optional, Sequence


def pick_callable(obj: Any, names: Sequence[str]):
    for name in names:
        fn = getattr(obj, name, None)
        if callable(fn):
            return fn
    return None


def call_router(router: Any, context: Dict[str, Any], user_input: str) -> Any:
    if not router:
        return None

    router_fn = pick_callable(router, ["route", "run", "handle", "__call__"])
    if router_fn is None:
        return None

    candidate_calls = [
        {"context": context, "user_input": user_input},
        {"context": context},
        {"user_input": user_input},
    ]

    for kwargs in candidate_calls:
        try:
            return router_fn(**kwargs)
        except TypeError:
            continue
        except Exception as e:
            return {"router_error": str(e)}

    try:
        return router_fn(context)
    except Exception as e:
        return {"router_error": str(e)}


def call_planner(
    planner: Any,
    context: Dict[str, Any],
    user_input: str,
    route: Any,
) -> Any:
    if not planner:
        return None

    planner_fn = pick_callable(
        planner,
        [
            "plan",
            "run",
            "create_plan",
            "build_plan",
            "build",
            "make_plan",
            "generate_plan",
            "generate",
            "handle",
            "__call__",
        ],
    )

    if planner_fn is None:
        return {
            "ok": False,
            "_planner_error": True,
            "error": "planner has no callable method",
        }

    candidate_calls = [
        {"context": context, "user_input": user_input, "route": route},
        {"context": context, "user_input": user_input},
        {"context": context},
        {"user_input": user_input, "route": route},
        {"user_input": user_input},
        {"input_text": user_input},
        {"message": user_input},
        {"prompt": user_input},
        {"task": context},
        {"payload": context},
    ]

    for kwargs in candidate_calls:
        try:
            return planner_fn(**kwargs)
        except TypeError:
            continue
        except Exception as e:
            return {
                "ok": False,
                "_planner_error": True,
                "error": f"planner 呼叫失敗: {e}",
                "traceback": traceback.format_exc(),
            }

    positional_calls = [
        context,
        user_input,
        {"context": context, "user_input": user_input, "route": route},
    ]

    for arg in positional_calls:
        try:
            return planner_fn(arg)
        except TypeError:
            continue
        except Exception as e:
            return {
                "ok": False,
                "_planner_error": True,
                "error": f"planner 呼叫失敗: {e}",
                "traceback": traceback.format_exc(),
            }

    return {
        "ok": False,
        "_planner_error": True,
        "error": "planner 存在，但沒有找到相容的呼叫方式",
    }


def call_llm_planner(
    llm_planner: Any,
    context: Dict[str, Any],
    user_input: str,
    route: Any,
) -> Any:
    if not llm_planner:
        return None

    planner_fn = pick_callable(
        llm_planner,
        [
            "plan",
            "run",
            "create_plan",
            "build_plan",
            "build",
            "make_plan",
            "generate_plan",
            "generate",
            "handle",
            "__call__",
        ],
    )

    if planner_fn is None:
        return {
            "ok": False,
            "_planner_error": True,
            "error": "llm_planner has no callable method",
        }

    candidate_calls = [
        {"context": context, "user_input": user_input, "route": route},
        {"context": context, "user_input": user_input},
        {"context": context},
        {"user_input": user_input, "route": route},
        {"user_input": user_input},
        {"input_text": user_input},
        {"message": user_input},
        {"prompt": user_input},
        {"task": context},
        {"payload": context},
    ]

    for kwargs in candidate_calls:
        try:
            return planner_fn(**kwargs)
        except TypeError:
            continue
        except Exception as e:
            return {
                "ok": False,
                "_planner_error": True,
                "error": f"llm_planner 呼叫失敗: {e}",
                "traceback": traceback.format_exc(),
            }

    positional_calls = [
        context,
        user_input,
        {"context": context, "user_input": user_input, "route": route},
    ]

    for arg in positional_calls:
        try:
            return planner_fn(arg)
        except TypeError:
            continue
        except Exception as e:
            return {
                "ok": False,
                "_planner_error": True,
                "error": f"llm_planner 呼叫失敗: {e}",
                "traceback": traceback.format_exc(),
            }

    return {
        "ok": False,
        "_planner_error": True,
        "error": "llm_planner 存在，但沒有找到相容的呼叫方式",
    }


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

    executor_fn = pick_callable(
        step_executor,
        [
            "execute",
            "run",
            "execute_step",
            "run_step",
            "execute_one_step",
            "handle",
            "__call__",
        ],
    )

    if executor_fn is None:
        return {"error": "step_executor has no callable method"}

    candidate_calls = [
        {
            "step": step,
            "context": context,
            "user_input": user_input,
            "route": route,
            "previous_result": previous_result,
            "step_index": step_index,
            "step_count": step_count,
        },
        {
            "step": step,
            "context": context,
            "previous_result": previous_result,
            "step_index": step_index,
            "step_count": step_count,
        },
        {
            "step": step,
            "context": context,
        },
        {
            "step": step,
        },
        {
            "payload": step,
        },
    ]

    for kwargs in candidate_calls:
        try:
            return executor_fn(**kwargs)
        except TypeError:
            continue
        except Exception as e:
            return {
                "error": f"step_executor 呼叫失敗: {e}",
                "traceback": traceback.format_exc(),
            }

    for arg in (step, context):
        try:
            return executor_fn(arg)
        except TypeError:
            continue
        except Exception as e:
            return {
                "error": f"step_executor 呼叫失敗: {e}",
                "traceback": traceback.format_exc(),
            }

    return {"error": "step_executor 存在，但沒有找到相容的呼叫方式"}


def run_verifier(verifier: Any, execution_result: Any) -> Any:
    if not verifier:
        return execution_result

    try:
        verify_fn = pick_callable(verifier, ["verify", "check", "review", "run"])
        if verify_fn is None:
            return execution_result

        try:
            return verify_fn(result=execution_result)
        except TypeError:
            try:
                return verify_fn(payload=execution_result)
            except TypeError:
                return verify_fn(execution_result)
    except Exception:
        return execution_result


def run_safety_guard(safety_guard: Any, execution_result: Any) -> Any:
    if not safety_guard:
        return execution_result

    try:
        guard_fn = pick_callable(safety_guard, ["check", "review", "evaluate", "run"])
        if guard_fn is None:
            return execution_result

        try:
            return guard_fn(result=execution_result)
        except TypeError:
            try:
                return guard_fn(payload=execution_result)
            except TypeError:
                return guard_fn(execution_result)
    except Exception:
        return execution_result