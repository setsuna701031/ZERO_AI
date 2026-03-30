# core/tasks/scheduler.py
from __future__ import annotations

import copy
import traceback
from typing import Any, Dict, List, Optional


try:
    from core.runtime.step_executor import StepExecutor
except Exception:
    StepExecutor = None  # type: ignore


try:
    from core.tasks.task_replanner import TaskReplanner
except Exception:
    TaskReplanner = None  # type: ignore


class Scheduler:
    """
    通用 Scheduler（相容舊 boot_system / ZeroSystem 呼叫方式）
    """

    def __init__(
        self,
        workspace_dir: str = "workspace",
        step_executor: Optional[Any] = None,
        runtime_store: Optional[Any] = None,
        planner: Optional[Any] = None,
        replanner: Optional[Any] = None,
        queue: Optional[List[Dict[str, Any]]] = None,  # ← 相容舊參數
        debug: bool = False,
        **kwargs,  # ← 吃掉其他舊參數，避免再炸
    ) -> None:
        self.workspace_root = workspace_dir
        self.runtime_store = runtime_store
        self.planner = planner
        self.debug = debug

        self.step_executor = step_executor or self._build_default_step_executor()
        self.replanner = replanner or self._build_default_replanner()

        self.queue: List[Dict[str, Any]] = queue or []
        self.current_task: Optional[Dict[str, Any]] = None
        self.last_result: Optional[Dict[str, Any]] = None

    # ============================================================
    # public
    # ============================================================

    def add_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize_task(task)
        self.queue.append(normalized)

        self._runtime_mark(
            event="scheduler_task_added",
            task=normalized,
            payload={
                "task_id": normalized.get("id"),
                "queue_size": len(self.queue),
            },
        )

        return {
            "ok": True,
            "task": normalized,
            "queue_size": len(self.queue),
        }

    def submit_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return self.add_task(task)

    def enqueue(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return self.add_task(task)

    def list_tasks(self) -> List[Dict[str, Any]]:
        return copy.deepcopy(self.queue)

    def get_queue(self) -> List[Dict[str, Any]]:
        return self.list_tasks()

    def has_tasks(self) -> bool:
        return len(self.queue) > 0

    def next_task(self) -> Optional[Dict[str, Any]]:
        if not self.queue:
            return None
        return self.queue.pop(0)

    def run_next(self) -> Dict[str, Any]:
        task = self.next_task()
        if task is None:
            return {
                "ok": True,
                "status": "idle",
                "message": "no task in queue",
            }
        return self.run_task(task)

    def run_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        normalized_task = self._normalize_task(task)
        self.current_task = normalized_task

        try:
            steps = self._extract_steps(normalized_task)

            if not steps:
                result = {
                    "ok": True,
                    "status": "completed",
                    "task": normalized_task,
                    "steps": [],
                    "execution_log": [],
                    "final_answer": normalized_task.get("goal")
                    or normalized_task.get("title")
                    or "task completed",
                }
                self.last_result = result
                return result

            if self.step_executor is None:
                return {
                    "ok": False,
                    "status": "failed",
                    "task": normalized_task,
                    "steps": steps,
                    "execution_log": [],
                    "final_answer": "Scheduler 沒有 step_executor。",
                }

            execution_log: List[Dict[str, Any]] = []
            last_step_result: Any = None

            for idx, step in enumerate(steps):
                normalized_task["current_step_index"] = idx
                normalized_task["current_step"] = step
                normalized_task["last_step_result"] = last_step_result

                step_result = self._execute_step(
                    step=step,
                    task=normalized_task,
                    previous_result=last_step_result,
                )

                normalized_step_result = self._normalize_step_result(
                    step=step,
                    step_index=idx,
                    raw_result=step_result,
                )
                execution_log.append(normalized_step_result)
                last_step_result = normalized_step_result.get("result")

                if normalized_step_result.get("ok") is False:
                    failed_result = {
                        "ok": False,
                        "status": "failed",
                        "task": normalized_task,
                        "steps": steps,
                        "execution_log": execution_log,
                        "final_answer": normalized_step_result.get("error") or "step failed",
                    }
                    self.last_result = failed_result
                    return failed_result

            final_answer = self._extract_final_answer(last_step_result)
            if not final_answer:
                final_answer = normalized_task.get("goal") or "task completed"

            result = {
                "ok": True,
                "status": "completed",
                "task": normalized_task,
                "steps": steps,
                "execution_log": execution_log,
                "final_answer": final_answer,
            }

            self.last_result = result
            return result

        except Exception as e:
            return {
                "ok": False,
                "status": "error",
                "task": normalized_task,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }
        finally:
            self.current_task = None

    def run(self) -> Dict[str, Any]:
        return self.run_next()

    # ============================================================
    # internal helpers
    # ============================================================

    def _build_default_step_executor(self) -> Optional[Any]:
        if StepExecutor is None:
            return None

        try:
            return StepExecutor(
                runtime_store=self.runtime_store,
                workspace_root=self.workspace_root,
                debug=self.debug,
            )
        except Exception:
            try:
                return StepExecutor()
            except Exception:
                return None

    def _build_default_replanner(self) -> Optional[Any]:
        if TaskReplanner is None:
            return None

        try:
            return TaskReplanner(workspace_dir=self.workspace_root)
        except Exception:
            try:
                return TaskReplanner()
            except Exception:
                return None

    def _normalize_task(self, task: Any) -> Dict[str, Any]:
        if isinstance(task, dict):
            normalized = copy.deepcopy(task)
        else:
            normalized = {
                "title": str(task),
                "goal": str(task),
            }

        normalized.setdefault("id", normalized.get("task_id"))
        normalized.setdefault("title", normalized.get("goal") or "untitled task")
        normalized.setdefault("goal", normalized.get("title"))
        normalized.setdefault("workspace", normalized.get("workspace") or self.workspace_root)
        normalized.setdefault("status", "pending")

        return normalized

    def _extract_steps(self, task: Dict[str, Any]) -> List[Any]:
        for key in ("steps", "plan", "actions", "tasks"):
            value = task.get(key)
            if isinstance(value, list):
                return value
        return []

    def _execute_step(
        self,
        step: Any,
        task: Dict[str, Any],
        previous_result: Any = None,
    ) -> Any:
        if self.step_executor is None:
            return {
                "ok": False,
                "error": "step_executor missing",
            }

        for method_name in ("execute_step", "execute_one_step", "run_step", "execute", "run"):
            fn = getattr(self.step_executor, method_name, None)
            if callable(fn):
                for kwargs in (
                    {"step": step, "task": task, "previous_result": previous_result},
                    {"step": step, "task": task},
                    {"step": step},
                ):
                    try:
                        return fn(**kwargs)
                    except TypeError:
                        continue
                    except Exception as e:
                        return {
                            "ok": False,
                            "error": str(e),
                            "traceback": traceback.format_exc(),
                        }

        return {
            "ok": False,
            "error": "no callable method on step_executor",
        }

    def _normalize_step_result(
        self,
        step: Any,
        step_index: int,
        raw_result: Any,
    ) -> Dict[str, Any]:
        if isinstance(raw_result, dict):
            result = copy.deepcopy(raw_result)
            result.setdefault("step_index", step_index)
            result.setdefault("step", step)
            result.setdefault("ok", True if "error" not in result else False)
            return result

        return {
            "step_index": step_index,
            "step": step,
            "ok": True,
            "result": raw_result,
        }

    def _extract_final_answer(self, value: Any) -> Optional[str]:
        if isinstance(value, str):
            return value

        if isinstance(value, dict):
            for key in ("final_answer", "answer", "message", "response", "summary"):
                v = value.get(key)
                if isinstance(v, str) and v.strip():
                    return v.strip()

        return None

    def _runtime_mark(
        self,
        event: str,
        task: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self.runtime_store is None:
            return

        task = task or {}
        payload = payload or {}

        for method_name in ("append_event", "log_event", "record_event", "write_event"):
            fn = getattr(self.runtime_store, method_name, None)
            if callable(fn):
                try:
                    fn(task_id=task.get("id"), event=event, payload=payload)
                    return
                except Exception:
                    continue