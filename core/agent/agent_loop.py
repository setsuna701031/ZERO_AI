from __future__ import annotations

import copy
import time
import traceback
from typing import Any, Dict, Optional

from core.memory.context_builder import build_context
from core.runtime.task_runner import TaskRunner


class AgentLoop:
    """
    ZERO Agent Loop

    目前收斂目標：
    1. 明確區分 single-shot 與 task mode
    2. task mode 只負責建立任務與交給 scheduler
    3. scheduler 呼叫 run_task() 時，只做單個 task 的 one-tick 執行
    4. 保留舊相容入口，但主幹改成清楚的 loop 骨架

    這一版不急著接 execution_trace。
    先把主流程固定成：
        detect mode
        -> build context
        -> route
        -> plan
        -> create/submit task
        -> scheduler tick
        -> task_runner.run_one_tick
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
    ) -> None:
        self.router = router
        self.planner = planner
        self.step_executor = step_executor
        self.verifier = verifier
        self.safety_guard = safety_guard
        self.memory_store = memory_store
        self.runtime_store = runtime_store

        # 相容舊入口：task_manager 還能存在，但 scheduler 是主要任務控制入口
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
    # public entry
    # ============================================================

    def run(self, user_input: str) -> Dict[str, Any]:
        """
        對外主入口：
        - 如果判定為 task mode：建立任務並送進 scheduler
        - 否則：走 single-shot
        """
        user_text = str(user_input or "").strip()
        if not user_text:
            return {"ok": False, "error": "empty input"}

        context = self._build_context(user_text)
        route = self._call_router(context=context, user_input=user_text)

        if self.debug:
            print("[AgentLoop] input =", user_text)
            print("[AgentLoop] route =", route)

        if self._should_enter_task_mode(route=route, user_input=user_text):
            return self._run_task_mode(
                context=context,
                user_input=user_text,
                route=route,
            )

        return self._run_single_shot_mode(
            context=context,
            user_input=user_text,
            route=route,
        )

    def run_task(
        self,
        task: Any,
        *,
        current_tick: int = 0,
        user_input: str = "",
        original_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        給 scheduler 呼叫的 one-tick task execution 入口。

        這裡不做 create / submit，不做 UI 回應，
        只做：
            normalize task
            -> task_runner.run_one_tick(...)
            -> return result
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

            effective_user_input = str(user_input or task_dict.get("goal") or "").strip()
            effective_original_plan = (
                original_plan
                if isinstance(original_plan, dict)
                else task_dict.get("planner_result")
            )

            if self.debug:
                print(
                    "[AgentLoop] run_task:",
                    task_dict.get("task_name") or task_dict.get("task_id") or task_dict.get("id"),
                    "tick=",
                    current_tick,
                )

            result = self.task_runner.run_one_tick(
                task=task_dict,
                current_tick=current_tick,
                user_input=effective_user_input,
                original_plan=effective_original_plan,
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
    # single-shot mode
    # ============================================================

    def _run_single_shot_mode(
        self,
        context: Dict[str, Any],
        user_input: str,
        route: Any,
    ) -> Dict[str, Any]:
        plan = self._call_planner(
            context=context,
            user_input=user_input,
            route=route,
        )

        if isinstance(plan, dict) and plan.get("ok") is False and plan.get("_planner_error"):
            return {
                "ok": False,
                "mode": "single_shot",
                "error": plan.get("error", "planner call failed"),
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
            plan = self._call_planner(
                context=context,
                user_input=user_input,
                route=route,
            )

            if isinstance(plan, dict) and plan.get("ok") is False and plan.get("_planner_error"):
                return {
                    "ok": False,
                    "mode": "task",
                    "error": plan.get("error", "planner call failed"),
                    "traceback": plan.get("traceback"),
                }

            if self._supports_scheduler_create_submit(task_entry):
                return self._run_task_mode_via_scheduler(
                    task_entry=task_entry,
                    context=context,
                    user_input=user_input,
                    route=route,
                    plan=plan,
                )

            return self._run_task_mode_legacy_enqueue(
                task_entry=task_entry,
                context=context,
                user_input=user_input,
                route=route,
                plan=plan,
            )

        except Exception as e:
            return {
                "ok": False,
                "mode": "task",
                "error": f"task mode failed: {e}",
                "traceback": traceback.format_exc(),
            }

    def _run_task_mode_via_scheduler(
        self,
        task_entry: Any,
        context: Dict[str, Any],
        user_input: str,
        route: Any,
        plan: Any,
    ) -> Dict[str, Any]:
        priority = self._route_int(route, "priority", 0)
        max_replans = self._route_int(route, "max_replans", 1)
        timeout_ticks = self._route_int(route, "timeout_ticks", 0)
        depends_on = self._route_depends_on(route)

        create_result = task_entry.create_task(
            goal=user_input,
            priority=priority,
            timeout_ticks=timeout_ticks,
            depends_on=depends_on,
        )

        if not isinstance(create_result, dict) or not create_result.get("ok"):
            return {
                "ok": False,
                "mode": "task",
                "error": (
                    create_result.get("error", "scheduler.create_task failed")
                    if isinstance(create_result, dict)
                    else "scheduler.create_task failed"
                ),
                "create_result": create_result,
            }

        created_task = create_result.get("task")
        if not isinstance(created_task, dict):
            task_id = str(create_result.get("task_name") or "").strip()
            created_task = self._get_task_from_entry(task_entry, task_id)
        else:
            created_task = self._normalize_task_input(created_task)

        if not isinstance(created_task, dict):
            return {
                "ok": False,
                "mode": "task",
                "error": "created task missing or invalid",
                "create_result": create_result,
            }

        created_task["planner_result"] = plan if isinstance(plan, dict) else {}
        created_task["steps"] = self._extract_steps_from_plan(plan)
        created_task["steps_total"] = len(created_task["steps"])
        created_task["final_answer"] = ""
        created_task["max_replans"] = max_replans

        if isinstance(route, dict):
            created_task["route"] = copy.deepcopy(route)
        if isinstance(context, dict):
            created_task["context_snapshot"] = copy.deepcopy(context)

        created_task.setdefault("results", [])
        created_task.setdefault("step_results", [])
        created_task.setdefault("execution_log", [])
        created_task.setdefault("last_step_result", None)
        created_task.setdefault("last_error", None)
        created_task.setdefault("current_step_index", 0)
        created_task.setdefault("replanned", False)
        created_task.setdefault("replan_reason", "")
        created_task.setdefault("replan_count", 0)

        self._save_task_plan_and_runtime(
            task=created_task,
            plan=created_task["planner_result"],
        )
        self._persist_task_to_entry(task_entry=task_entry, task=created_task)

        task_id = str(
            created_task.get("task_id")
            or created_task.get("id")
            or created_task.get("task_name")
            or ""
        ).strip()

        submit_result = task_entry.submit_existing_task(task_id)
        refreshed_task = self._get_task_from_entry(task_entry, task_id) or created_task

        return {
            "ok": True,
            "mode": "task",
            "context": context,
            "route": route,
            "task": refreshed_task,
            "task_id": task_id,
            "task_dir": refreshed_task.get("task_dir"),
            "plan": refreshed_task.get("planner_result"),
            "create_result": create_result,
            "submit_result": submit_result,
            "final_answer": f"已建立任務：{refreshed_task.get('title') or refreshed_task.get('goal')}",
        }

    def _run_task_mode_legacy_enqueue(
        self,
        task_entry: Any,
        context: Dict[str, Any],
        user_input: str,
        route: Any,
        plan: Any,
    ) -> Dict[str, Any]:
        task = self._build_task_shell(
            user_input=user_input,
            context=context,
            route=route,
        )

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

        task["planner_result"] = plan if isinstance(plan, dict) else {}
        task["steps"] = self._extract_steps_from_plan(plan)
        task["steps_total"] = len(task["steps"])
        task["final_answer"] = ""

        if self.task_workspace is not None:
            try:
                self.task_workspace.save_plan(task, task["planner_result"])
            except Exception:
                pass

        if self.task_runtime is not None:
            try:
                self.task_runtime.ensure_runtime_state(task)
            except Exception:
                pass

        enqueue_result = self._enqueue_task(task_entry, task)

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

    # ============================================================
    # loop helpers
    # ============================================================

    def _build_context(self, user_input: str) -> Dict[str, Any]:
        context = build_context(
            user_input=user_input,
            memory_store=self.memory_store,
            runtime_store=self.runtime_store,
        )
        if self.debug:
            print("[AgentLoop] context =", context)
        return context

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
                return copy.deepcopy(plan["steps"])

            nested_plan = plan.get("plan")
            if isinstance(nested_plan, dict) and isinstance(nested_plan.get("steps"), list):
                return copy.deepcopy(nested_plan["steps"])

            for key in ("actions", "tasks"):
                value = plan.get(key)
                if isinstance(value, list):
                    return copy.deepcopy(value)

        if isinstance(plan, list):
            return copy.deepcopy(plan)

        return []

    def _make_task_id(self) -> str:
        return f"task_{int(time.time() * 1000)}"

    # ============================================================
    # task shell
    # ============================================================

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
            "status": "created",
            "priority": 0,
            "retry_count": 0,
            "max_retries": 0,
            "retry_delay": 0,
            "timeout_ticks": 0,
            "depends_on": [],
            "simulate": "",
            "required_ticks": 1,
            "progress_ticks": 0,
            "history": ["created"],
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
            task["route"] = copy.deepcopy(route)

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

            depends_on = route.get("depends_on")
            if isinstance(depends_on, list):
                task["depends_on"] = [str(x).strip() for x in depends_on if str(x).strip()]
            elif isinstance(depends_on, str) and depends_on.strip():
                task["depends_on"] = [depends_on.strip()]

        if isinstance(context, dict):
            task["context_snapshot"] = copy.deepcopy(context)

        return task

    # ============================================================
    # controlled scheduler helpers
    # ============================================================

    def _supports_scheduler_create_submit(self, task_entry: Any) -> bool:
        create_fn = getattr(task_entry, "create_task", None)
        submit_fn = getattr(task_entry, "submit_existing_task", None)
        return callable(create_fn) and callable(submit_fn)

    def _persist_task_to_entry(self, task_entry: Any, task: Dict[str, Any]) -> None:
        task_id = str(
            task.get("task_id")
            or task.get("id")
            or task.get("task_name")
            or ""
        ).strip()
        if not task_id:
            return

        persist_fn = getattr(task_entry, "_persist_task_payload", None)
        if callable(persist_fn):
            try:
                persist_fn(task_id=task_id, task=copy.deepcopy(task))
                return
            except Exception:
                pass

        repo = getattr(task_entry, "task_repo", None)
        if repo is not None:
            replace_fn = getattr(repo, "replace_task", None)
            upsert_fn = getattr(repo, "upsert_task", None)
            create_fn = getattr(repo, "create_task", None)
            add_fn = getattr(repo, "add_task", None)

            try:
                if callable(replace_fn):
                    replace_fn(task_id, copy.deepcopy(task))
                    return
                if callable(upsert_fn):
                    upsert_fn(copy.deepcopy(task))
                    return
                if callable(create_fn):
                    create_fn(copy.deepcopy(task))
                    return
                if callable(add_fn):
                    add_fn(copy.deepcopy(task))
                    return
            except Exception:
                pass

    def _get_task_from_entry(self, task_entry: Any, task_id: str) -> Optional[Dict[str, Any]]:
        if not task_id:
            return None

        get_fn = getattr(task_entry, "_get_task_from_repo", None)
        if callable(get_fn):
            try:
                value = get_fn(task_id)
                if isinstance(value, dict):
                    return copy.deepcopy(value)
            except Exception:
                pass

        repo = getattr(task_entry, "task_repo", None)
        if repo is not None:
            for method_name in ("get_task", "get", "load_task", "find_task"):
                fn = getattr(repo, method_name, None)
                if callable(fn):
                    try:
                        value = fn(task_id)
                        if isinstance(value, dict):
                            return copy.deepcopy(value)
                    except Exception:
                        pass

        return None

    def _save_task_plan_and_runtime(self, task: Dict[str, Any], plan: Any) -> None:
        workspace = self.task_workspace
        runtime = self.task_runtime

        if workspace is None:
            workspace = getattr(self.scheduler, "task_workspace", None)

        if runtime is None:
            runtime = getattr(self.scheduler, "task_runtime", None)

        if workspace is not None:
            try:
                workspace.save_plan(task, plan if isinstance(plan, dict) else {})
            except Exception:
                pass
            try:
                workspace.save_task_snapshot(task)
            except Exception:
                pass

        if runtime is not None:
            try:
                runtime.ensure_runtime_state(task)
            except Exception:
                pass

    def _enqueue_task(self, task_entry: Any, task: Dict[str, Any]) -> Any:
        for method_name in ("add_task", "enqueue", "submit_task", "create_task"):
            fn = getattr(task_entry, method_name, None)
            if callable(fn):
                return fn(task)
        raise RuntimeError("scheduler/task_manager has no add_task / enqueue / submit_task / create_task")

    def _route_int(self, route: Any, key: str, default: int) -> int:
        if isinstance(route, dict) and route.get(key) is not None:
            try:
                return int(route.get(key))
            except Exception:
                return default
        return default

    def _route_depends_on(self, route: Any) -> Optional[list]:
        if not isinstance(route, dict):
            return None

        value = route.get("depends_on")
        if value is None:
            return None

        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]

        if isinstance(value, str) and value.strip():
            return [value.strip()]

        return None

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

        to_dict = getattr(task, "to_dict", None)
        if callable(to_dict):
            result = to_dict()
            if isinstance(result, dict):
                return copy.deepcopy(result)

        if hasattr(task, "__dict__"):
            raw = dict(vars(task))
            if isinstance(raw, dict):
                return copy.deepcopy(raw)

        if isinstance(task, dict):
            return copy.deepcopy(task)

        raise TypeError("task must be dict-like or object with to_dict()")