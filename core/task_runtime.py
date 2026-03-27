from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.memory_manager import MemoryManager
from core.planner import Planner
from core.reflection_engine import ReflectionEngine
from core.task_state_machine import TaskStateMachine


class TaskRuntime:
    """
    ZERO Task Runtime (Memory-aware + State Machine + Timeline) v3

    負責：
    - 讀 lessons
    - planner.plan(goal, lessons=...)
    - 逐步執行 steps
    - 寫入 state.json / timeline.jsonl / plan.json / step_XX.json / result.json / lesson.json / log.txt
    - execution 後 reflect -> save lesson
    - state task_type 與 runtime 同步
    """

    def __init__(
        self,
        workspace_root: Path | str,
        task_manager: Any = None,
        tool_registry: Any = None,
        planner: Optional[Planner] = None,
        memory_manager: Optional[MemoryManager] = None,
        reflection_engine: Optional[ReflectionEngine] = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.task_manager = task_manager
        self.tool_registry = tool_registry

        self.planner = planner or Planner()
        self.memory_manager = memory_manager or MemoryManager(workspace_root=self.workspace_root)
        self.reflection_engine = reflection_engine or ReflectionEngine()

    # =========================================================
    # Run Task
    # =========================================================

    def run_task(self, task_info: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(task_info, dict):
            raise TypeError("task_info must be a dict.")

        task_name = str(task_info.get("task_name", "")).strip()
        goal = str(task_info.get("goal", "")).strip()

        if not task_name:
            raise ValueError("task_info['task_name'] is required.")

        task_dir = self.workspace_root / task_name
        task_dir.mkdir(parents=True, exist_ok=True)

        initial_task_type = str(task_info.get("task_type", "general")).strip() or "general"
        state_machine = TaskStateMachine(task_dir=task_dir)

        state_machine.initialize(
            task_name=task_name,
            goal=goal,
            task_type=initial_task_type,
            force_new_run=False,
            extra_fields={
                "run_mode": str(task_info.get("run_mode", "normal")).strip() or "normal",
                "source_task_name": str(task_info.get("source_task_name", "")).strip(),
            },
        )

        step_results: List[Dict[str, Any]] = []
        plan: Dict[str, Any] = {}

        try:
            self._set_task_status(task_name, "running")
            self._append_log(task_dir, f"Task started: {task_name}")
            self._append_log(task_dir, f"Goal: {goal}")
            self._save_json(task_dir / "task.json", task_info)

            state_machine.append_event(
                event_type="task_started",
                message="Task runtime started.",
                data={"task_name": task_name},
            )

            # 1) task type 判定
            task_type = self._classify_task_type(goal)
            state_machine.patch_state(
                {
                    "task_type": task_type,
                },
                message="Task type synchronized to runtime classification.",
            )
            state_machine.append_event(
                event_type="task_classified",
                message="Task type classified.",
                data={"task_type": task_type},
            )

            # 2) planning
            state_machine.transition(
                new_state="planning",
                message="Planning started.",
                data={"task_type": task_type},
            )

            lessons = self.memory_manager.get_relevant_lessons(
                goal=goal,
                task_type=task_type,
                limit=5,
            )
            self._save_json(task_dir / "recalled_lessons.json", {"lessons": lessons})
            self._append_log(task_dir, f"Loaded {len(lessons)} lesson(s) for planning.")

            state_machine.append_event(
                event_type="lessons_loaded",
                message="Relevant lessons loaded.",
                data={
                    "lesson_count": len(lessons),
                    "lesson_ids": [
                        str(item.get("lesson_id", "")).strip()
                        for item in lessons
                        if isinstance(item, dict)
                    ],
                },
            )

            plan = self.planner.plan(goal=goal, lessons=lessons)
            self._save_json(task_dir / "plan.json", plan)

            steps = plan.get("steps", [])
            if not isinstance(steps, list):
                raise ValueError("plan['steps'] must be a list.")

            task_type = str(plan.get("task_type", task_type)).strip() or "general"

            state_machine.patch_state(
                {
                    "task_type": task_type,
                    "planner_version": str(plan.get("planner_version", "unknown")),
                    "planned_step_count": len(steps),
                },
                message="Task state synchronized to planner output.",
            )

            state_machine.append_event(
                event_type="plan_generated",
                message="Plan generated.",
                data={
                    "planner_version": plan.get("planner_version", "unknown"),
                    "step_count": len(steps),
                    "task_type": task_type,
                },
            )

            # 3) running
            state_machine.transition(
                new_state="running",
                message="Execution started.",
                data={"step_count": len(steps), "task_type": task_type},
            )

            for index, step in enumerate(steps, start=1):
                if not isinstance(step, dict):
                    raise ValueError(f"plan step must be dict, got: {type(step).__name__}")

                state_machine.append_event(
                    event_type="step_started",
                    message=f"Step {index} started.",
                    data={
                        "step": index,
                        "step_name": str(step.get("name", f"step_{index}")),
                        "step_kind": str(step.get("kind", "reason")),
                        "tool_name": self._normalize_tool_name(step.get("tool_name")),
                    },
                )

                step_result = self._execute_step(
                    step_index=index,
                    step=step,
                    goal=goal,
                    task_type=task_type,
                )
                step_results.append(step_result)

                self._save_json(task_dir / f"step_{index:02d}.json", step_result)
                self._append_log(
                    task_dir,
                    f"Step {index:02d} finished: {step_result.get('step_text', '')}",
                )

                state_machine.append_event(
                    event_type="step_finished",
                    message=f"Step {index} finished.",
                    data={
                        "step": index,
                        "step_text": step_result.get("step_text", ""),
                        "step_kind": step_result.get("step_kind", ""),
                        "status": step_result.get("status", ""),
                        "tool_name": step_result.get("tool_name"),
                    },
                )

                self._raise_if_step_failed(step_result)

            # 4) reflecting
            state_machine.transition(
                new_state="reflecting",
                message="Reflection started.",
                data={"step_count": len(step_results), "task_type": task_type},
            )

            result_payload = self._build_final_result(
                task_name=task_name,
                goal=goal,
                task_type=task_type,
                step_results=step_results,
                plan=plan,
                state_machine=state_machine,
            )
            self._save_json(task_dir / "result.json", result_payload)

            self._reflect_and_persist_lesson(
                task_info=task_info,
                runtime_result={
                    "success": True,
                    "summary": f"Task finished: {task_name}",
                    "task_type": task_type,
                    "tools_used": result_payload["tools_used"],
                    "data": result_payload,
                    "error": None,
                },
                step_results=step_results,
                plan=plan,
                task_dir=task_dir,
                state_machine=state_machine,
            )

            # 5) finished
            state_machine.transition(
                new_state="finished",
                message="Task finished successfully.",
                data={"task_name": task_name, "task_type": task_type},
            )

            self._append_log(task_dir, "Task finished.")
            self._set_task_status(task_name, "finished")

            final_state = state_machine.read_state()

            return {
                "success": True,
                "summary": f"Task finished: {task_name}",
                "task_type": task_type,
                "tools_used": result_payload["tools_used"],
                "data": {
                    "task_name": task_name,
                    "task_dir": str(task_dir),
                    "status": "finished",
                    "task_type": task_type,
                    "current_state": final_state.get("current_state", "finished"),
                    "planner_version": plan.get("planner_version", "unknown"),
                    "plan_file": str(task_dir / "plan.json"),
                    "result_file": str(task_dir / "result.json"),
                    "log_file": str(task_dir / "log.txt"),
                    "lesson_file": str(task_dir / "lesson.json"),
                    "state_file": str(task_dir / "state.json"),
                    "timeline_file": str(task_dir / "timeline.jsonl"),
                    "step_count": len(step_results),
                    "step_files": [
                        str(task_dir / f"step_{i:02d}.json")
                        for i in range(1, len(step_results) + 1)
                    ],
                    "tools_used": result_payload["tools_used"],
                    "tool_step_count": result_payload["tool_step_count"],
                    "tool_success_count": result_payload["tool_success_count"],
                    "tool_failure_count": result_payload["tool_failure_count"],
                    "all_tool_steps_succeeded": result_payload["all_tool_steps_succeeded"],
                    "memory_lesson_count": len(lessons),
                    "recalled_lesson_ids": plan.get("memory_context", {}).get(
                        "recalled_lesson_ids", []
                    ),
                },
                "error": None,
            }

        except Exception as exc:
            self._append_log(task_dir, f"Task failed: {exc}")
            self._set_task_status(task_name, "failed")

            try:
                state_machine.transition(
                    new_state="failed",
                    message="Task failed.",
                    data={"error": str(exc), "task_type": self._classify_task_type(goal)},
                )
            except Exception:
                pass

            failed_result = {
                "task_name": task_name,
                "goal": goal,
                "task_type": self._classify_task_type(goal),
                "status": "failed",
                "message": str(exc),
                "steps": step_results,
            }
            self._save_json(task_dir / "result.json", failed_result)

            runtime_result = {
                "success": False,
                "summary": f"Task failed: {task_name}",
                "task_type": self._classify_task_type(goal),
                "tools_used": self._collect_tools_used(step_results),
                "data": {
                    "task_name": task_name,
                    "task_dir": str(task_dir),
                    "status": "failed",
                    "current_state": state_machine.read_state().get("current_state", "failed"),
                    "result_file": str(task_dir / "result.json"),
                    "log_file": str(task_dir / "log.txt"),
                    "lesson_file": str(task_dir / "lesson.json"),
                    "state_file": str(task_dir / "state.json"),
                    "timeline_file": str(task_dir / "timeline.jsonl"),
                    "step_count": len(step_results),
                },
                "error": str(exc),
            }

            self._reflect_and_persist_lesson(
                task_info=task_info,
                runtime_result=runtime_result,
                step_results=step_results,
                plan=plan,
                task_dir=task_dir,
                state_machine=state_machine,
            )

            return runtime_result

    # =========================================================
    # Reflection / Memory
    # =========================================================

    def _reflect_and_persist_lesson(
        self,
        task_info: Dict[str, Any],
        runtime_result: Dict[str, Any],
        step_results: List[Dict[str, Any]],
        plan: Dict[str, Any],
        task_dir: Path,
        state_machine: TaskStateMachine,
    ) -> None:
        try:
            state_machine.append_event(
                event_type="reflection_started",
                message="Reflection engine started.",
                data={"task_name": task_info.get("task_name", "")},
            )

            lesson = self.reflection_engine.reflect(
                task_info=task_info,
                runtime_result=runtime_result,
                step_results=step_results,
                planner_context=plan.get("memory_context", {}) if isinstance(plan, dict) else {},
            )
            self._save_json(task_dir / "lesson.json", lesson)
            save_result = self.memory_manager.save_lesson(lesson)
            self._append_log(task_dir, "Lesson reflected and saved.")

            lesson_id = ""
            if isinstance(save_result, dict):
                lesson_id = str(save_result.get("data", {}).get("lesson_id", "")).strip()

            state_machine.append_event(
                event_type="lesson_saved",
                message="Lesson saved to memory.",
                data={
                    "lesson_id": lesson_id,
                    "outcome": lesson.get("outcome", ""),
                },
            )
        except Exception as exc:
            self._append_log(task_dir, f"Lesson save skipped: {exc}")
            state_machine.append_event(
                event_type="lesson_save_skipped",
                message="Lesson save skipped.",
                data={"error": str(exc)},
            )

    # =========================================================
    # Step Execution
    # =========================================================

    def _execute_step(
        self,
        step_index: int,
        step: Dict[str, Any],
        goal: str,
        task_type: str,
    ) -> Dict[str, Any]:
        step_text = str(step.get("name", f"step_{step_index}"))
        step_kind = str(step.get("kind", "reason")).strip().lower() or "reason"
        raw_tool_name = step.get("tool_name")
        tool_name = self._normalize_tool_name(raw_tool_name)
        tool_args = step.get("tool_args", {})

        if not isinstance(tool_args, dict):
            tool_args = {}

        if step_kind == "tool":
            output = self._execute_tool_step(
                step_text=step_text,
                tool_name=tool_name,
                tool_args=tool_args,
                goal=goal,
                task_type=task_type,
            )
        else:
            output = self._execute_reason_step(
                step_text=step_text,
                goal=goal,
                task_type=task_type,
            )

        step_status = self._derive_step_status(step_kind=step_kind, output=output)

        return {
            "step": step_index,
            "step_text": step_text,
            "step_kind": step_kind,
            "task_type": task_type,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "status": step_status,
            "output": output,
        }

    def _execute_tool_step(
        self,
        step_text: str,
        tool_name: Optional[str],
        tool_args: Dict[str, Any],
        goal: str,
        task_type: str,
    ) -> Dict[str, Any]:
        clean_tool_name = self._normalize_tool_name(tool_name)

        if not clean_tool_name:
            return {
                "tool_name": None,
                "tool_args": tool_args,
                "tool_found": False,
                "tool_success": False,
                "error": "Tool step missing valid tool_name.",
                "note": "Planned tool step had no usable tool name.",
            }

        tool = self._get_tool(clean_tool_name)
        if tool is None:
            return {
                "tool_name": clean_tool_name,
                "tool_args": tool_args,
                "tool_found": False,
                "tool_success": False,
                "error": f"Tool not found: {clean_tool_name}",
                "note": "Tool step was planned but no registered tool was found.",
            }

        try:
            tool_result = self._run_tool(tool, tool_args)

            tool_success = True
            if isinstance(tool_result, dict) and tool_result.get("success") is False:
                tool_success = False

            return {
                "tool_name": clean_tool_name,
                "tool_args": tool_args,
                "tool_found": True,
                "tool_success": tool_success,
                "step_text": step_text,
                "goal": goal,
                "task_type": task_type,
                "tool_result": tool_result,
            }
        except Exception as exc:
            return {
                "tool_name": clean_tool_name,
                "tool_args": tool_args,
                "tool_found": True,
                "tool_success": False,
                "step_text": step_text,
                "goal": goal,
                "task_type": task_type,
                "error": str(exc),
            }

    def _execute_reason_step(
        self,
        step_text: str,
        goal: str,
        task_type: str,
    ) -> Dict[str, Any]:
        normalized_step = step_text.strip().lower()

        if normalized_step.startswith("memory precheck:"):
            hint = step_text.split(":", 1)[1].strip() if ":" in step_text else step_text
            return {
                "memory_precheck": hint,
                "status": "recorded",
            }

        if task_type == "command":
            return self._execute_command_reason_step(normalized_step, step_text, goal)

        if task_type == "file":
            return self._execute_file_reason_step(normalized_step, step_text, goal)

        return self._execute_general_reason_step(normalized_step, step_text, goal)

    def _execute_command_reason_step(
        self,
        normalized_step: str,
        step_text: str,
        goal: str,
    ) -> Dict[str, Any]:
        if normalized_step == "analyze goal":
            return {
                "goal": goal,
                "analysis": "Detected command-oriented task.",
            }

        if normalized_step == "validate command target":
            return {
                "validation": "Command text prepared for execution.",
            }

        if normalized_step == "collect command result":
            return {
                "collection": "Command result collection finished.",
            }

        if normalized_step == "save result":
            return {
                "save": "Command task result prepared for persistence.",
            }

        return {
            "info": f"Unhandled command reason step executed as generic step: {step_text}",
        }

    def _execute_file_reason_step(
        self,
        normalized_step: str,
        step_text: str,
        goal: str,
    ) -> Dict[str, Any]:
        if normalized_step == "analyze goal":
            return {
                "goal": goal,
                "analysis": "Detected file-oriented task.",
            }

        if normalized_step == "verify file path":
            return {
                "validation": "File path check stage completed.",
            }

        if normalized_step == "summarize file handling":
            return {
                "summary": "File handling summary prepared.",
            }

        if normalized_step == "save result":
            return {
                "save": "File task result prepared for persistence.",
            }

        return {
            "info": f"Unhandled file reason step executed as generic step: {step_text}",
        }

    def _execute_general_reason_step(
        self,
        normalized_step: str,
        step_text: str,
        goal: str,
    ) -> Dict[str, Any]:
        if normalized_step == "analyze goal":
            return {
                "goal": goal,
                "analysis": f"Goal received: {goal}",
            }

        if normalized_step == "plan response":
            return {
                "plan": "Response plan created (memory-aware rules v1).",
            }

        if normalized_step == "summarize outcome":
            return {
                "summary": "Outcome summary prepared.",
            }

        if normalized_step == "save result":
            return {
                "save": "General task result prepared for persistence.",
            }

        return {
            "info": f"Unhandled general reason step executed as generic step: {step_text}",
        }

    # =========================================================
    # Failure Control
    # =========================================================

    def _derive_step_status(self, step_kind: str, output: Any) -> str:
        if step_kind == "tool":
            if isinstance(output, dict) and output.get("tool_success") is True:
                return "finished"
            return "failed"
        return "finished"

    def _raise_if_step_failed(self, step_result: Dict[str, Any]) -> None:
        if not isinstance(step_result, dict):
            raise RuntimeError("Invalid step_result: must be dict.")

        step_kind = str(step_result.get("step_kind", "")).strip().lower()
        if step_kind != "tool":
            return

        output = step_result.get("output", {})
        if not isinstance(output, dict):
            raise RuntimeError(
                f"Tool step failed: invalid output format in step {step_result.get('step')}"
            )

        if output.get("tool_success") is True:
            return

        tool_name = self._normalize_tool_name(step_result.get("tool_name")) or "unknown_tool"
        error_message = str(output.get("error", "Unknown tool execution error.")).strip()
        step_text = str(step_result.get("step_text", "")).strip()

        tool_result = output.get("tool_result", {})
        if isinstance(tool_result, dict):
            nested_error = str(tool_result.get("error", "")).strip()
            if nested_error:
                error_message = nested_error

        raise RuntimeError(
            f"Tool step failed: step='{step_text}', tool='{tool_name}', error='{error_message}'"
        )

    # =========================================================
    # Final Result
    # =========================================================

    def _build_final_result(
        self,
        task_name: str,
        goal: str,
        task_type: str,
        step_results: List[Dict[str, Any]],
        plan: Dict[str, Any],
        state_machine: TaskStateMachine,
    ) -> Dict[str, Any]:
        tool_summary = self._build_tool_execution_summary(step_results)
        current_state = state_machine.read_state().get("current_state", "reflecting")

        return {
            "task_name": task_name,
            "goal": goal,
            "task_type": task_type,
            "status": "finished",
            "current_state": current_state,
            "message": "Task finished (memory-aware runtime + state machine)",
            "planner_version": plan.get("planner_version", "unknown"),
            "memory_context": plan.get("memory_context", {}),
            "step_count": len(step_results),
            "tools_used": tool_summary["tools_used"],
            "tool_step_count": tool_summary["tool_step_count"],
            "tool_success_count": tool_summary["tool_success_count"],
            "tool_failure_count": tool_summary["tool_failure_count"],
            "all_tool_steps_succeeded": tool_summary["all_tool_steps_succeeded"],
            "steps": step_results,
        }

    # =========================================================
    # Tool Helpers
    # =========================================================

    def _get_tool(self, name: str) -> Optional[Any]:
        clean_name = self._normalize_tool_name(name)
        if not clean_name or self.tool_registry is None:
            return None

        get_tool = getattr(self.tool_registry, "get_tool", None)
        if callable(get_tool):
            tool = get_tool(clean_name)
            if tool is not None:
                return tool

        tools = getattr(self.tool_registry, "tools", None)
        if isinstance(tools, dict):
            return tools.get(clean_name)

        private_tools = getattr(self.tool_registry, "_tools", None)
        if isinstance(private_tools, dict):
            return private_tools.get(clean_name)

        return None

    def _run_tool(self, tool: Any, tool_args: Dict[str, Any]) -> Any:
        execute_method = getattr(tool, "execute", None)
        if callable(execute_method):
            try:
                return execute_method(tool_args)
            except TypeError:
                pass

        run_method = getattr(tool, "run", None)
        if callable(run_method):
            return run_method(**tool_args)

        call_method = getattr(tool, "__call__", None)
        if callable(call_method):
            return call_method(**tool_args)

        raise RuntimeError(
            f"Tool '{getattr(tool, 'name', str(tool))}' has no callable execute/run method."
        )

    def _collect_tools_used(self, step_results: List[Dict[str, Any]]) -> List[str]:
        names: List[str] = []

        for item in step_results:
            if not isinstance(item, dict):
                continue

            clean_tool_name = self._normalize_tool_name(item.get("tool_name"))
            if clean_tool_name and clean_tool_name not in names:
                names.append(clean_tool_name)

        return names

    def _build_tool_execution_summary(self, step_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        tools_used = self._collect_tools_used(step_results)

        tool_step_count = 0
        tool_success_count = 0
        tool_failure_count = 0

        for item in step_results:
            if not isinstance(item, dict):
                continue

            step_kind = str(item.get("step_kind", "")).strip().lower()
            clean_tool_name = self._normalize_tool_name(item.get("tool_name"))

            if step_kind != "tool" and not clean_tool_name:
                continue

            tool_step_count += 1

            output = item.get("output", {})
            if isinstance(output, dict) and output.get("tool_success") is True:
                tool_success_count += 1
            else:
                tool_failure_count += 1

        return {
            "tools_used": tools_used,
            "tool_step_count": tool_step_count,
            "tool_success_count": tool_success_count,
            "tool_failure_count": tool_failure_count,
            "all_tool_steps_succeeded": (
                tool_failure_count == 0 if tool_step_count > 0 else True
            ),
        }

    # =========================================================
    # Parsing Helpers
    # =========================================================

    def _classify_task_type(self, goal: str) -> str:
        lowered = goal.lower()

        command_keywords = [
            "cmd:",
            "command",
            "execute",
            "run ",
            "shell",
            "terminal",
            "powershell",
            "執行",
            "指令",
            "命令",
            "echo ",
            "dir ",
            "copy ",
            "move ",
        ]

        file_keywords = [
            "ws:",
            ".py",
            ".json",
            ".txt",
            ".md",
            "file",
            "folder",
            "workspace",
            "path",
            "檔案",
            "資料夾",
            "路徑",
            "讀取",
            "讀檔",
        ]

        if any(keyword in lowered for keyword in command_keywords):
            return "command"

        if any(keyword in lowered for keyword in file_keywords):
            return "file"

        return "general"

    def _normalize_tool_name(self, value: Any) -> Optional[str]:
        if value is None:
            return None

        text = str(value).strip()
        if not text:
            return None

        if text.lower() == "none":
            return None

        return text

    # =========================================================
    # Helpers
    # =========================================================

    def _set_task_status(self, task_name: str, status: str) -> None:
        if self.task_manager is None:
            return

        update_method = getattr(self.task_manager, "update_task_status", None)
        if callable(update_method):
            try:
                update_method(task_name, status)
                return
            except Exception:
                pass

        set_method = getattr(self.task_manager, "set_task_status", None)
        if callable(set_method):
            try:
                set_method(task_name, status)
                return
            except Exception:
                pass

    def _save_json(self, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _append_log(self, task_dir: Path, text: str) -> None:
        task_dir.mkdir(parents=True, exist_ok=True)
        log_file = task_dir / "log.txt"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(text + "\n")