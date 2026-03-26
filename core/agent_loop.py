from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.memory_manager import MemoryManager
from core.reflection_engine import ReflectionDecision, ReflectionEngine
from core.task_manager import TaskManager
from core.task_runtime import TaskRuntime


MAX_RETRY_PER_TASK = 2
MAX_REFLECTION_PER_TASK = 1


@dataclass
class AgentLoopResult:
    ok: bool
    status: str
    message: str
    root_task_id: Optional[str] = None
    current_task_id: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "message": self.message,
            "root_task_id": self.root_task_id,
            "current_task_id": self.current_task_id,
            "result": self.result,
            "error": self.error,
            "data": self.data or {},
        }


class AgentLoop:
    """
    Agent Loop + Retry + Reflection/Replan v1

    目前能力：
    - 建立 root task
    - planner 拆 subtasks
    - executor 執行 leaf task
    - runtime 記錄事件
    - memory 記錄任務開始 / step 完成 / step 失敗 / root summary
    - step 失敗時自動 retry
    - retry 用完後進行 reflection
    - reflection 產生補救 subtasks，讓任務繼續跑
    - summary 會記錄執行歷程，不只看最終樹狀狀態
    - lessons 會自動去重
    """

    def __init__(
        self,
        task_manager: TaskManager,
        task_runtime: TaskRuntime,
        planner: Optional[Any] = None,
        executor: Optional[Any] = None,
        memory_manager: Optional[MemoryManager] = None,
        reflection_engine: Optional[ReflectionEngine] = None,
    ) -> None:
        self.task_manager = task_manager
        self.task_runtime = task_runtime
        self.planner = planner
        self.executor = executor
        self.memory_manager = memory_manager
        self.reflection_engine = reflection_engine or ReflectionEngine()

        self._retry_counter: Dict[str, int] = {}
        self._reflection_counter: Dict[str, int] = {}

    # -------------------------------------------------------------------------
    # 對外主流程
    # -------------------------------------------------------------------------
    def start_new_task(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentLoopResult:
        if not user_input or not user_input.strip():
            return AgentLoopResult(
                ok=False,
                status="invalid_input",
                message="User input is empty.",
                error="empty_user_input",
            )

        root_task_id = self.task_manager.create_root_task(
            title=user_input.strip(),
            meta={"source": "user_input"},
        )
        self.task_runtime.set_active_root_task(root_task_id)
        self.task_runtime.set_current_task(None)
        self.task_runtime.log_info(
            message=f"Created root task: {user_input.strip()}",
            task_id=root_task_id,
        )

        planned = self._ensure_root_subtasks(
            root_task_id=root_task_id,
            user_input=user_input,
            context=context,
        )
        if not planned.ok:
            return planned

        subtasks = self.task_manager.get_children(root_task_id)
        subtask_titles = [item["title"] for item in subtasks]

        if self.memory_manager is not None:
            self.memory_manager.record_task_started(
                root_task_id=root_task_id,
                goal=user_input.strip(),
                subtasks=subtask_titles,
                context=context,
            )

        return AgentLoopResult(
            ok=True,
            status="task_started",
            message="Root task created and subtasks prepared.",
            root_task_id=root_task_id,
            data={"tree": self.task_manager.get_tree_snapshot(root_task_id)},
        )

    def run_next_step(
        self,
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentLoopResult:
        root_task_id = self.task_runtime.get_active_root_task()
        if not root_task_id:
            return AgentLoopResult(
                ok=False,
                status="no_active_task",
                message="No active root task.",
                error="no_active_root_task",
            )

        if self.task_manager.is_task_tree_completed(root_task_id):
            self.task_runtime.set_current_task(None)
            self._record_root_summary_if_needed(root_task_id)
            return AgentLoopResult(
                ok=True,
                status="all_completed",
                message="Task tree already completed.",
                root_task_id=root_task_id,
                data={"tree": self.task_manager.get_tree_snapshot(root_task_id)},
            )

        next_task = self.task_manager.get_next_runnable_task(root_id=root_task_id)
        if not next_task:
            if self.task_manager.is_task_tree_failed(root_task_id):
                self.task_runtime.set_current_task(None)
                self._record_root_summary_if_needed(root_task_id)
                return AgentLoopResult(
                    ok=False,
                    status="task_tree_failed",
                    message="Task tree contains failed task.",
                    root_task_id=root_task_id,
                    error="task_tree_failed",
                    data={"tree": self.task_manager.get_tree_snapshot(root_task_id)},
                )

            return AgentLoopResult(
                ok=False,
                status="no_runnable_task",
                message="No runnable task found.",
                root_task_id=root_task_id,
                error="no_runnable_task",
                data={"tree": self.task_manager.get_tree_snapshot(root_task_id)},
            )

        task_id = next_task["id"]
        self.task_runtime.set_current_task(task_id)
        self.task_manager.mark_task_running(task_id)
        self.task_runtime.log_info(
            message=f"Running task: {next_task['title']}",
            task_id=task_id,
        )

        execution = self._execute_leaf_task(next_task, context=context)

        if not execution.ok:
            if self.task_manager.is_task_tree_failed(root_task_id):
                self.task_runtime.set_current_task(None)
                self._record_root_summary_if_needed(root_task_id)
            return AgentLoopResult(
                ok=False,
                status=execution.status,
                message=execution.message,
                root_task_id=root_task_id,
                current_task_id=task_id,
                error=execution.error,
                data={"tree": self.task_manager.get_tree_snapshot(root_task_id)},
            )

        if self.task_manager.is_task_tree_completed(root_task_id):
            self.task_runtime.set_current_task(None)
            self._record_root_summary_if_needed(root_task_id)
            return AgentLoopResult(
                ok=True,
                status="all_completed",
                message="Task tree completed.",
                root_task_id=root_task_id,
                current_task_id=task_id,
                result=execution.result,
                data={"tree": self.task_manager.get_tree_snapshot(root_task_id)},
            )

        return AgentLoopResult(
            ok=True,
            status=execution.status,
            message=execution.message,
            root_task_id=root_task_id,
            current_task_id=task_id,
            result=execution.result,
            data={
                "tree": self.task_manager.get_tree_snapshot(root_task_id),
                **(execution.data or {}),
            },
        )

    def run_until_done(
        self,
        context: Optional[Dict[str, Any]] = None,
        max_steps: int = 50,
    ) -> AgentLoopResult:
        if max_steps <= 0:
            return AgentLoopResult(
                ok=False,
                status="invalid_max_steps",
                message="max_steps must be greater than 0.",
                error="invalid_max_steps",
            )

        root_task_id = self.task_runtime.get_active_root_task()
        if not root_task_id:
            return AgentLoopResult(
                ok=False,
                status="no_active_task",
                message="No active root task.",
                error="no_active_root_task",
            )

        steps_run = 0

        while steps_run < max_steps:
            step_result = self.run_next_step(context=context)
            steps_run += 1

            if step_result.status == "all_completed":
                return AgentLoopResult(
                    ok=True,
                    status="all_completed",
                    message=f"Task tree completed in {steps_run} step(s).",
                    root_task_id=root_task_id,
                    current_task_id=step_result.current_task_id,
                    result=step_result.result,
                    data={
                        "steps_run": steps_run,
                        "tree": self.task_manager.get_tree_snapshot(root_task_id),
                    },
                )

            if not step_result.ok:
                return AgentLoopResult(
                    ok=False,
                    status=step_result.status,
                    message=step_result.message,
                    root_task_id=root_task_id,
                    current_task_id=step_result.current_task_id,
                    error=step_result.error,
                    data={
                        "steps_run": steps_run,
                        "tree": self.task_manager.get_tree_snapshot(root_task_id),
                    },
                )

        return AgentLoopResult(
            ok=False,
            status="max_steps_reached",
            message=f"Stopped after reaching max_steps={max_steps}.",
            root_task_id=root_task_id,
            current_task_id=self.task_runtime.get_current_task(),
            error="max_steps_reached",
            data={
                "steps_run": steps_run,
                "tree": self.task_manager.get_tree_snapshot(root_task_id),
            },
        )

    def get_active_tree(self) -> Optional[Dict[str, Any]]:
        root_task_id = self.task_runtime.get_active_root_task()
        if not root_task_id:
            return None
        return self.task_manager.get_tree_snapshot(root_task_id)

    def reset_active_task(self) -> None:
        self.task_runtime.reset()
        self._retry_counter.clear()
        self._reflection_counter.clear()

    # -------------------------------------------------------------------------
    # 內部：拆任務
    # -------------------------------------------------------------------------
    def _ensure_root_subtasks(
        self,
        root_task_id: str,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentLoopResult:
        if self.task_manager.has_subtasks(root_task_id):
            return AgentLoopResult(
                ok=True,
                status="subtasks_already_exist",
                message="Subtasks already exist.",
                root_task_id=root_task_id,
            )

        subtask_titles = self._plan_subtasks(user_input=user_input, context=context)
        if not subtask_titles:
            return AgentLoopResult(
                ok=False,
                status="planning_failed",
                message="Planner did not return any subtasks.",
                root_task_id=root_task_id,
                error="empty_plan",
            )

        for index, title in enumerate(subtask_titles, start=1):
            self.task_manager.add_subtask(
                parent_id=root_task_id,
                title=title,
                meta={"step_index": index},
            )

        self.task_runtime.log_info(
            message=f"Planned {len(subtask_titles)} subtasks.",
            task_id=root_task_id,
            count=len(subtask_titles),
        )

        return AgentLoopResult(
            ok=True,
            status="subtasks_created",
            message="Subtasks created successfully.",
            root_task_id=root_task_id,
        )

    def _plan_subtasks(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        if self.planner is None:
            return [user_input.strip()]

        try:
            if hasattr(self.planner, "plan") and callable(self.planner.plan):
                raw = self.planner.plan(user_input, context=context)
            elif callable(self.planner):
                raw = self.planner(user_input, context)
            else:
                return [user_input.strip()]
        except Exception:
            return [user_input.strip()]

        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]

        if isinstance(raw, dict):
            if isinstance(raw.get("steps"), list):
                return [str(item).strip() for item in raw["steps"] if str(item).strip()]
            if isinstance(raw.get("subtasks"), list):
                return [str(item).strip() for item in raw["subtasks"] if str(item).strip()]

        if isinstance(raw, str) and raw.strip():
            return [raw.strip()]

        return [user_input.strip()]

    # -------------------------------------------------------------------------
    # 內部：執行任務 + retry + reflection
    # -------------------------------------------------------------------------
    def _execute_leaf_task(
        self,
        task: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentLoopResult:
        task_id = task["id"]
        task_title = task["title"]
        root_task_id = self.task_runtime.get_active_root_task()

        initial_retry_count = self._retry_counter.get(task_id, 0)

        while self._retry_counter.get(task_id, 0) <= MAX_RETRY_PER_TASK:
            try:
                result_text = self._call_executor(task=task, context=context)
                result_text = self._normalize_result_text(result_text)

                self.task_manager.mark_task_completed(task_id, result=result_text)
                self.task_runtime.record_step_result(task_id, result_text)
                self.task_runtime.log_info(
                    message=f"Task completed: {task_title}",
                    task_id=task_id,
                    retry_count=self._retry_counter.get(task_id, 0),
                )

                if self.memory_manager is not None and root_task_id is not None:
                    self.memory_manager.record_step_completed(
                        root_task_id=root_task_id,
                        task_id=task_id,
                        task_title=task_title,
                        result=result_text,
                        meta={
                            "status": "completed",
                            "retry_count": self._retry_counter.get(task_id, 0),
                        },
                    )

                return AgentLoopResult(
                    ok=True,
                    status="task_completed",
                    message=f"Task completed: {task_title}",
                    root_task_id=root_task_id,
                    current_task_id=task_id,
                    result=result_text,
                    data={
                        "retry_count": self._retry_counter.get(task_id, 0),
                        "retried": self._retry_counter.get(task_id, 0) > 0,
                        "initial_retry_count": initial_retry_count,
                    },
                )

            except Exception as exc:
                error_text = f"{type(exc).__name__}: {exc}"
                current_retry = self._retry_counter.get(task_id, 0) + 1
                self._retry_counter[task_id] = current_retry

                self.task_runtime.record_step_error(task_id, error_text)

                if current_retry <= MAX_RETRY_PER_TASK:
                    self.task_runtime.log_warning(
                        message=f"Task failed, retrying ({current_retry}/{MAX_RETRY_PER_TASK}): {task_title}",
                        task_id=task_id,
                        error=error_text,
                        retry_count=current_retry,
                    )

                    self.task_manager.mark_task_pending(task_id)

                    if self.memory_manager is not None and root_task_id is not None:
                        self.memory_manager.record_step_failed(
                            root_task_id=root_task_id,
                            task_id=task_id,
                            task_title=task_title,
                            error=error_text,
                            meta={
                                "status": "retrying",
                                "retry_count": current_retry,
                                "max_retry": MAX_RETRY_PER_TASK,
                            },
                        )

                    self.task_manager.mark_task_running(task_id)
                    continue

                reflection_result = self._handle_reflection_after_retry_exhausted(
                    task=task,
                    error_text=error_text,
                    context=context,
                )
                return reflection_result

        return AgentLoopResult(
            ok=False,
            status="retry_loop_error",
            message="Retry loop exited unexpectedly.",
            root_task_id=root_task_id,
            current_task_id=task_id,
            error="retry_loop_error",
        )

    def _handle_reflection_after_retry_exhausted(
        self,
        task: Dict[str, Any],
        error_text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentLoopResult:
        task_id = task["id"]
        task_title = task["title"]
        root_task_id = self.task_runtime.get_active_root_task()

        current_reflection_count = self._reflection_counter.get(task_id, 0) + 1
        self._reflection_counter[task_id] = current_reflection_count

        if current_reflection_count > MAX_REFLECTION_PER_TASK:
            self.task_manager.mark_task_failed(task_id, error=error_text)
            self.task_runtime.log_error(
                message=f"Task permanently failed after reflection limit: {task_title}",
                task_id=task_id,
                error=error_text,
                reflection_count=current_reflection_count,
            )

            if self.memory_manager is not None and root_task_id is not None:
                self.memory_manager.record_step_failed(
                    root_task_id=root_task_id,
                    task_id=task_id,
                    task_title=task_title,
                    error=error_text,
                    meta={
                        "status": "failed",
                        "retry_count": self._retry_counter.get(task_id, 0),
                        "reflection_count": current_reflection_count,
                        "max_retry": MAX_RETRY_PER_TASK,
                        "max_reflection": MAX_REFLECTION_PER_TASK,
                    },
                )

            return AgentLoopResult(
                ok=False,
                status="task_failed",
                message=f"Task failed after retries and reflection limit: {task_title}",
                root_task_id=root_task_id,
                current_task_id=task_id,
                error=error_text,
                data={
                    "retry_count": self._retry_counter.get(task_id, 0),
                    "reflection_count": current_reflection_count,
                },
            )

        self.task_runtime.log_warning(
            message=f"Retry exhausted, starting reflection: {task_title}",
            task_id=task_id,
            error=error_text,
            retry_count=self._retry_counter.get(task_id, 0),
            reflection_count=current_reflection_count,
        )

        decision: ReflectionDecision = self.reflection_engine.reflect(
            task=task,
            error=error_text,
            context=context,
        )

        if not decision.ok or decision.action != "replan" or not decision.generated_steps:
            self.task_manager.mark_task_failed(task_id, error=error_text)
            self.task_runtime.log_error(
                message=f"Reflection could not recover task: {task_title}",
                task_id=task_id,
                error=error_text,
                reflection=decision.to_dict(),
            )

            if self.memory_manager is not None and root_task_id is not None:
                self.memory_manager.record_step_failed(
                    root_task_id=root_task_id,
                    task_id=task_id,
                    task_title=task_title,
                    error=error_text,
                    meta={
                        "status": "failed_after_reflection",
                        "retry_count": self._retry_counter.get(task_id, 0),
                        "reflection_count": current_reflection_count,
                        "reflection": decision.to_dict(),
                    },
                )

            return AgentLoopResult(
                ok=False,
                status="task_failed",
                message=f"Task failed and reflection could not recover: {task_title}",
                root_task_id=root_task_id,
                current_task_id=task_id,
                error=error_text,
                data={
                    "retry_count": self._retry_counter.get(task_id, 0),
                    "reflection_count": current_reflection_count,
                    "reflection": decision.to_dict(),
                },
            )

        generated_ids: List[str] = []
        base_step_index = len(self.task_manager.get_children(task_id))

        for offset, step_title in enumerate(decision.generated_steps, start=1):
            new_task_id = self.task_manager.add_subtask(
                parent_id=task_id,
                title=step_title,
                meta={
                    "step_index": base_step_index + offset,
                    "source": "reflection_replan",
                    "reflection_parent": task_id,
                },
            )
            generated_ids.append(new_task_id)

        self.task_manager.set_task_error(task_id, None)
        self.task_manager.set_task_result(task_id, None)
        self.task_manager.mark_task_pending(task_id)

        self.task_runtime.log_info(
            message=f"Reflection replanned task: {task_title}",
            task_id=task_id,
            generated_steps=len(decision.generated_steps),
            reflection=decision.to_dict(),
        )

        if self.memory_manager is not None and root_task_id is not None:
            self.memory_manager.record_step_failed(
                root_task_id=root_task_id,
                task_id=task_id,
                task_title=task_title,
                error=error_text,
                meta={
                    "status": "replanned",
                    "retry_count": self._retry_counter.get(task_id, 0),
                    "reflection_count": current_reflection_count,
                    "reflection": decision.to_dict(),
                    "generated_task_ids": generated_ids,
                },
            )

        return AgentLoopResult(
            ok=True,
            status="task_replanned",
            message=f"Task replanned after reflection: {task_title}",
            root_task_id=root_task_id,
            current_task_id=task_id,
            result=decision.summary,
            data={
                "retry_count": self._retry_counter.get(task_id, 0),
                "reflection_count": current_reflection_count,
                "reflection": decision.to_dict(),
                "generated_task_ids": generated_ids,
            },
        )

    def _call_executor(
        self,
        task: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        if self.executor is None:
            return f"Simulated completion: {task['title']}"

        if hasattr(self.executor, "execute_task") and callable(self.executor.execute_task):
            return self.executor.execute_task(task, context=context)

        if callable(self.executor):
            return self.executor(task, context)

        return f"Simulated completion: {task['title']}"

    # -------------------------------------------------------------------------
    # 內部：記錄 summary（修正版：記錄歷程 + lessons 去重）
    # -------------------------------------------------------------------------
    def _record_root_summary_if_needed(self, root_task_id: str) -> None:
        if self.memory_manager is None:
            return

        existing = self.memory_manager.get_records_by_root_task(root_task_id)
        if any(item.get("memory_type") == "task_summary" for item in existing):
            return

        tree = self.task_manager.get_tree_snapshot(root_task_id)
        goal = tree.get("title", "")

        completed_steps: List[Dict[str, Any]] = []
        failed_steps: List[Dict[str, Any]] = []
        recovered_steps: List[Dict[str, Any]] = []
        replanned_steps: List[Dict[str, Any]] = []

        total_nodes = 0
        completed_count = 0
        failed_count = 0
        retry_total = 0
        reflection_total = 0
        failed_attempts = 0

        def walk(node: Dict[str, Any]) -> None:
            nonlocal total_nodes
            nonlocal completed_count
            nonlocal failed_count
            nonlocal retry_total
            nonlocal reflection_total
            nonlocal failed_attempts

            task_id = str(node.get("id", ""))
            title = str(node.get("title", ""))
            status = str(node.get("status", ""))
            result = node.get("result")
            error = node.get("error")
            meta = dict(node.get("meta", {}) or {})
            children = node.get("children_nodes", []) or []

            retry_count = int(self._retry_counter.get(task_id, 0) or 0)
            reflection_count = int(self._reflection_counter.get(task_id, 0) or 0)

            total_nodes += 1
            retry_total += retry_count
            reflection_total += reflection_count
            failed_attempts += retry_count

            item = {
                "task_id": task_id,
                "task_title": title,
                "result": result,
                "error": error,
                "status": status,
                "retry_count": retry_count,
                "reflection_count": reflection_count,
                "meta": meta,
            }

            if status == "completed":
                completed_steps.append(item)
                completed_count += 1
            elif status == "failed":
                failed_steps.append(item)
                failed_count += 1

            if retry_count > 0 and status == "completed":
                recovered_steps.append(item)

            if reflection_count > 0 or meta.get("source") == "reflection_replan":
                replanned_steps.append(item)

            for child in children:
                walk(child)

        walk(tree)

        final_status = str(tree.get("status", "unknown"))

        lessons_raw: List[str] = []

        if retry_total > 0:
            lessons_raw.append("Some steps failed initially but later succeeded after retry.")

        if reflection_total > 0:
            lessons_raw.append("Some steps required reflection and replanning to recover.")

        if failed_count > 0:
            lessons_raw.append("Some steps still ended in failed status.")

        if retry_total == 0 and reflection_total == 0 and failed_count == 0 and final_status == "completed":
            lessons_raw.append("Task completed smoothly without retries or reflection.")

        lessons = self._dedupe_preserve_order(lessons_raw)

        history_summary = {
            "goal": goal,
            "final_status": final_status,
            "stats": {
                "total_nodes": total_nodes,
                "completed_nodes": completed_count,
                "failed_nodes": failed_count,
                "failed_attempts": failed_attempts,
                "retry_total": retry_total,
                "reflection_total": reflection_total,
                "recovered_steps": len(recovered_steps),
                "replanned_steps": len(replanned_steps),
            },
            "completed_steps": completed_steps,
            "failed_steps": failed_steps,
            "recovered_steps": recovered_steps,
            "replanned_steps": replanned_steps,
            "lessons": lessons,
        }

        self.memory_manager.record_task_completed_summary(
            root_task_id=root_task_id,
            goal=goal,
            completed_steps=completed_steps,
            failed_steps=failed_steps,
            final_status=final_status,
            extra_summary=history_summary,
        )

    @staticmethod
    def _normalize_result_text(raw: Any) -> str:
        if raw is None:
            return "Task completed."
        if isinstance(raw, str):
            text = raw.strip()
            return text if text else "Task completed."
        if isinstance(raw, dict):
            if "result" in raw and raw["result"] is not None:
                return str(raw["result"])
            return str(raw)
        return str(raw)

    @staticmethod
    def _dedupe_preserve_order(items: List[str]) -> List[str]:
        seen = set()
        result: List[str] = []
        for item in items:
            text = str(item).strip()
            if not text:
                continue
            if text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result