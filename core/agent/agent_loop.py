from __future__ import annotations

import copy
import time
import traceback
from typing import Any, Dict, Optional

from core.memory.context_builder import build_context
from core.runtime.task_runner import TaskRunner


class AgentLoop:
    """
    Agent 主迴圈

    支援兩種模式：

    1. single-shot mode
       user_input
       -> build_context
       -> router
       -> planner
       -> step_executor
       -> verifier
       -> safety_guard
       -> response

    2. task mode
       user_input
       -> build_context
       -> router
       -> planner
       -> task workspace
       -> task runtime
       -> scheduler/task_manager.enqueue
       -> 回傳 task_id / task_created

    3. task execution mode
       scheduler
       -> agent_loop.run_task(task)
       -> task_runner.run_one_tick(...)
       -> task_runtime / runtime_state.json
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
        scheduler=None,
        task_manager=None,
        task_workspace=None,
        task_runtime=None,
        task_runner=None,
        replanner=None,
        debug: bool = False,
        **kwargs,
    ):
        self.router = router
        self.planner = planner
        self.step_executor = step_executor
        self.verifier = verifier
        self.safety_guard = safety_guard
        self.memory_store = memory_store
        self.runtime_store = runtime_store

        # 相容舊測試：task_manager 優先當作任務入口
        self.task_manager = task_manager
        self.scheduler = scheduler or task_manager

        self.task_workspace = task_workspace
        self.task_runtime = task_runtime
        self.replanner = replanner

        self.debug = debug
        self.extra_kwargs = kwargs

        self.task_runner = task_runner or TaskRunner(
            task_runtime=self.task_runtime,
            step_executor=self.step_executor,
            replanner=self.replanner,
            verifier=self.verifier,
            debug=self.debug,
        )

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

        # --------------------------------------------------------
        # task mode
        # --------------------------------------------------------
        if self._should_enter_task_mode(route=route, user_input=user_input):
            return self._run_task_mode(
                context=context,
                user_input=user_input,
                route=route,
            )

        # --------------------------------------------------------
        # single-shot mode（原本流程）
        # --------------------------------------------------------
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
                "mode": "single_shot",
                "context": context,
                "route": route,
                "final_answer": user_input,
            }

        execution_result = self._call_step_executor(
            plan=plan,
            context=context,
            user_input=user_input,
            route=route,
        )

        execution_result = self._run_verifier(execution_result)
        execution_result = self._run_safety_guard(execution_result)

        return {
            "ok": True,
            "mode": "single_shot",
            "context": context,
            "route": route,
            "plan": plan,
            "execution": execution_result,
            "final_answer": self._extract_final_answer(execution_result, plan, user_input),
        }

    # ============================================================
    # scheduler entry: execute one task tick
    # ============================================================

    def run_task(
        self,
        task: Any,
        *,
        current_tick: int = 0,
        user_input: str = "",
        original_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        給 scheduler 呼叫：
        AgentLoop.run_task(task) -> TaskRunner.run_one_tick(...)
        """

        try:
            task_dict = self._normalize_task_input(task)

            if not isinstance(task_dict, dict):
                return {
                    "ok": False,
                    "status": "failed",
                    "error": "task must be dict-like",
                }

            if self.task_runner is None:
                return {
                    "ok": False,
                    "status": "failed",
                    "error": "task_runner missing",
                }

            if self.debug:
                print(
                    "[AgentLoop] run_task ->",
                    task_dict.get("task_name") or task_dict.get("id"),
                    "tick=",
                    current_tick,
                )

            result = self.task_runner.run_one_tick(
                task=task_dict,
                current_tick=current_tick,
                user_input=user_input or task_dict.get("goal", ""),
                original_plan=original_plan or task_dict.get("planner_result"),
            )

            return result

        except Exception as e:
            return {
                "ok": False,
                "status": "failed",
                "error": f"agent_loop.run_task failed: {e}",
                "traceback": traceback.format_exc(),
            }

    # ============================================================
    # task mode
    # ============================================================

    def _run_task_mode(
        self,
        context: Dict[str, Any],
        user_input: str,
        route: Any,
    ) -> Dict[str, Any]:
        task_entry = self.scheduler or self.task_manager
        if task_entry is None:
            return {
                "ok": False,
                "mode": "task",
                "error": "scheduler/task_manager missing",
            }

        if self.planner is None:
            return {
                "ok": False,
                "mode": "task",
                "error": "planner missing",
            }

        try:
            task = self._build_task_shell(
                user_input=user_input,
                context=context,
                route=route,
            )

            # 1. 建立 workspace（如果有）
            if self.task_workspace is not None:
                try:
                    task = self.task_workspace.create_workspace(task)
                except Exception as e:
                    return {
                        "ok": False,
                        "mode": "task",
                        "error": f"task_workspace.create_workspace failed: {e}",
                        "traceback": traceback.format_exc(),
                    }

            # 2. 建立 plan
            plan = self._call_planner(
                context=context,
                user_input=user_input,
                route=route,
            )

            if isinstance(plan, dict) and plan.get("ok") is False and plan.get("_planner_error"):
                return {
                    "ok": False,
                    "mode": "task",
                    "error": plan.get("error", "planner 呼叫失敗"),
                    "traceback": plan.get("traceback"),
                }

            task["planner_result"] = plan if isinstance(plan, dict) else {}
            task["steps"] = self._extract_steps_from_plan(plan)
            task["steps_total"] = len(task["steps"])
            task["final_answer"] = self._extract_final_answer(None, plan, user_input)

            # 3. 存 plan.json（如果有）
            if self.task_workspace is not None:
                try:
                    self.task_workspace.save_plan(task, task["planner_result"])
                except Exception:
                    pass

            # 4. 初始化 runtime_state.json（如果有）
            if self.task_runtime is not None:
                try:
                    self.task_runtime.ensure_runtime_state(task)
                except Exception:
                    pass

            # 5. enqueue 到 scheduler / task_manager
            enqueue_result = self._enqueue_task(task_entry, task)

            # 6. 若 enqueue 回傳的是 Task 物件，轉成 dict 比較穩
            enqueued_task_dict = self._normalize_task_input(enqueue_result) if enqueue_result is not None else None

            if isinstance(enqueued_task_dict, dict):
                task = enqueued_task_dict

            return {
                "ok": True,
                "mode": "task",
                "context": context,
                "route": route,
                "task": task,
                "task_id": task.get("task_id") or task.get("id") or task.get("task_name"),
                "task_dir": task.get("task_dir"),
                "plan": task.get("planner_result"),
                "enqueue_result": enqueue_result,
                "final_answer": f"已建立任務：{task.get('title') or task.get('goal')}",
            }

        except Exception as e:
            return {
                "ok": False,
                "mode": "task",
                "error": f"task mode failed: {e}",
                "traceback": traceback.format_exc(),
            }

    def _build_task_shell(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
        route: Any = None,
    ) -> Dict[str, Any]:
        task_id = self._make_task_id()
        task_name = task_id

        workspace_dir = "workspace/tasks"
        task_dir = f"{workspace_dir}/{task_name}"
        runtime_state_file = f"{task_dir}/runtime_state.json"
        plan_file = f"{task_dir}/plan.json"
        log_file = f"{task_dir}/task.log"

        task: Dict[str, Any] = {
            "id": task_id,
            "task_id": task_id,
            "task_name": task_name,
            "title": user_input,
            "goal": user_input,
            "status": "queued",
            "priority": 0,
            "retry_count": 0,
            "max_retries": 0,
            "retry_delay": 0,
            "timeout_ticks": 0,
            "depends_on": [],
            "simulate": "",
            "required_ticks": 1,
            "progress_ticks": 0,
            "history": ["queued"],
            "workspace_dir": workspace_dir,
            "task_dir": task_dir,
            "runtime_state_file": runtime_state_file,
            "plan_file": plan_file,
            "log_file": log_file,
            "max_replans": 1,
            "replanned": False,
            "replan_reason": "",
            "replan_count": 0,
            "current_step_index": 0,
            "steps_total": 0,
            "steps": [],
            "results": [],
            "step_results": [],
            "execution_log": [],
            "last_step_result": None,
            "last_error": None,
            "current_step": None,
            "final_result": None,
            "final_answer": "",
        }

        if isinstance(route, dict):
            task["route"] = route

            if route.get("priority") is not None:
                try:
                    task["priority"] = int(route.get("priority", 0))
                except Exception:
                    pass

            if route.get("max_replans") is not None:
                try:
                    task["max_replans"] = int(route.get("max_replans", 1))
                except Exception:
                    pass

            if route.get("timeout_ticks") is not None:
                try:
                    task["timeout_ticks"] = int(route.get("timeout_ticks", 0))
                except Exception:
                    pass

        if isinstance(context, dict):
            task["context_snapshot"] = context

        return task

    def _enqueue_task(self, task_entry: Any, task: Dict[str, Any]) -> Any:
        for method_name in ("add_task", "submit_task", "enqueue", "create_task"):
            fn = getattr(task_entry, method_name, None)
            if callable(fn):
                return fn(task)

        raise RuntimeError("scheduler/task_manager has no add_task / submit_task / enqueue / create_task")

    def _should_enter_task_mode(self, route: Any, user_input: str) -> bool:
        if isinstance(route, dict):
            if route.get("mode") == "task":
                return True
            if route.get("type") == "task":
                return True
            if route.get("task") is True:
                return True
            if route.get("long_running") is True:
                return True

        text = str(user_input or "").strip().lower()

        task_keywords = [
            "建立任務",
            "新增任務",
            "排程",
            "加入佇列",
            "背景執行",
            "長任務",
            "task",
            "schedule",
            "queue",
            "background",
        ]

        return any(k in text for k in task_keywords)

    def _extract_steps_from_plan(self, plan: Any) -> list:
        if isinstance(plan, dict):
            if isinstance(plan.get("steps"), list):
                return plan["steps"]

            nested_plan = plan.get("plan")
            if isinstance(nested_plan, dict) and isinstance(nested_plan.get("steps"), list):
                return nested_plan["steps"]

            for key in ("actions", "tasks"):
                value = plan.get(key)
                if isinstance(value, list):
                    return value

        if isinstance(plan, list):
            return plan

        return []

    def _make_task_id(self) -> str:
        return f"task_{int(time.time() * 1000)}"

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
    # verifier / safety
    # ============================================================

    def _run_verifier(self, execution_result: Any) -> Any:
        if not self.verifier:
            return execution_result

        try:
            verify_fn = self._pick_callable(self.verifier, ["verify", "check", "review", "run"])
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

    def _run_safety_guard(self, execution_result: Any) -> Any:
        if not self.safety_guard:
            return execution_result

        try:
            guard_fn = self._pick_callable(self.safety_guard, ["check", "review", "evaluate", "run"])
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

    def _normalize_task_input(self, task: Any) -> Dict[str, Any]:
        if task is None:
            raise ValueError("task is None")

        # dataclass / object with to_dict
        to_dict = getattr(task, "to_dict", None)
        if callable(to_dict):
            result = to_dict()
            if isinstance(result, dict):
                return copy.deepcopy(result)

        # dataclass / object with __dict__
        if hasattr(task, "__dict__"):
            raw = dict(vars(task))
            if isinstance(raw, dict):
                return copy.deepcopy(raw)

        if isinstance(task, dict):
            return copy.deepcopy(task)

        raise TypeError("task must be dict-like or object with to_dict()")