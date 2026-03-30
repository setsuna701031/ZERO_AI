# core/agent/agent_loop.py
from __future__ import annotations

import traceback
from typing import Any, Dict, Optional

from core.memory.context_builder import build_context


class AgentLoop:
    """
    Agent 主迴圈

    流程：
        user_input
        -> build_context
        -> router
        -> planner
        -> step_executor
        -> verifier
        -> safety_guard
        -> response
    """

    def __init__(
        self,
        router=None,
        planner=None,
        step_executor=None,
        verifier=None,
        safety_guard=None,
        memory_store=None,
        runtime_store=None,
        debug: bool = False,
    ):
        self.router = router
        self.planner = planner
        self.step_executor = step_executor
        self.verifier = verifier
        self.safety_guard = safety_guard
        self.memory_store = memory_store
        self.runtime_store = runtime_store
        self.debug = debug

    # ============================================================
    # main entry
    # ============================================================

    def run(self, user_input: str) -> Dict[str, Any]:
        if not user_input:
            return {"ok": False, "error": "empty input"}

        context = build_context(
            user_input=user_input,
            memory_store=self.memory_store,
            runtime_store=self.runtime_store,
        )

        if self.debug:
            print("CTX:", context)

        route = self._call_router(context=context, user_input=user_input)

        plan = self._call_planner(
            context=context,
            user_input=user_input,
            route=route,
        )

        if isinstance(plan, dict) and plan.get("ok") is False and plan.get("_planner_error"):
            return {
                "ok": False,
                "error": plan.get("error", "planner 呼叫失敗"),
                "traceback": plan.get("traceback"),
            }

        if plan is None:
            return {
                "ok": True,
                "final_answer": user_input,
                "context": context,
                "route": route,
            }

        execution_result = self._call_step_executor(
            plan=plan,
            context=context,
            user_input=user_input,
            route=route,
        )

        if self.verifier:
            try:
                verify_fn = self._pick_callable(self.verifier, ["verify", "check", "review", "run"])
                if verify_fn is not None:
                    try:
                        execution_result = verify_fn(result=execution_result)
                    except TypeError:
                        try:
                            execution_result = verify_fn(payload=execution_result)
                        except TypeError:
                            execution_result = verify_fn(execution_result)
            except Exception:
                pass

        if self.safety_guard:
            try:
                guard_fn = self._pick_callable(self.safety_guard, ["check", "review", "evaluate", "run"])
                if guard_fn is not None:
                    try:
                        execution_result = guard_fn(result=execution_result)
                    except TypeError:
                        try:
                            execution_result = guard_fn(payload=execution_result)
                        except TypeError:
                            execution_result = guard_fn(execution_result)
            except Exception:
                pass

        return {
            "ok": True,
            "context": context,
            "route": route,
            "plan": plan,
            "execution": execution_result,
            "final_answer": self._extract_final_answer(execution_result, plan, user_input),
        }

    # ============================================================
    # router
    # ============================================================

    def _call_router(self, context: Dict[str, Any], user_input: str) -> Any:
        if not self.router:
            return None

        router_fn = self._pick_callable(self.router, ["route", "run", "handle", "__call__"])
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

    # ============================================================
    # planner
    # ============================================================

    def _call_planner(
        self,
        context: Dict[str, Any],
        user_input: str,
        route: Any,
    ) -> Any:
        if not self.planner:
            return None

        planner_fn = self._pick_callable(
            self.planner,
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

    # ============================================================
    # step executor
    # ============================================================

    def _call_step_executor(
        self,
        plan: Any,
        context: Dict[str, Any],
        user_input: str,
        route: Any,
    ) -> Any:
        if not self.step_executor:
            return None

        executor_fn = self._pick_callable(
            self.step_executor,
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
            {"plan": plan, "context": context, "user_input": user_input, "route": route},
            {"step": plan, "context": context, "user_input": user_input, "route": route},
            {"plan": plan, "context": context},
            {"step": plan, "context": context},
            {"plan": plan},
            {"step": plan},
            {"payload": plan},
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

        for arg in (plan, context):
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

    # ============================================================
    # utils
    # ============================================================

    def _pick_callable(self, obj: Any, names: list[str]):
        for name in names:
            fn = getattr(obj, name, None)
            if callable(fn):
                return fn
        return None

    def _extract_final_answer(self, execution: Any, plan: Any, fallback: str) -> str:
        for source in (execution, plan):
            if isinstance(source, dict):
                for key in ("final_answer", "answer", "response", "message", "summary"):
                    value = source.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()

            if isinstance(source, str) and source.strip():
                return source.strip()

        return fallback