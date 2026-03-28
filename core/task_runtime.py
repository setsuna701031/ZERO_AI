from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class TaskRuntime:
    """
    ZERO Task Runtime

    功能：
    - run_task_slice(...)：每次只跑一個 step
    - run_task(...)：相容模式，整個任務跑到底
    - pause_task(...)
    - resume_task(...)
    - runtime_state.json 持久化執行進度

    這版重點：
    - 明確支援 ws: / cmd: 任務
    - 工具步驟失敗時，會先進 retrying（若還有 retry）
    - retry 時會回退失敗步驟
    - 超過最大重試次數才會 failed
    """

    def __init__(
        self,
        workspace_root: Path | str,
        task_manager: Any = None,
        tool_registry: Any = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.task_manager = task_manager
        self.tool_registry = tool_registry
        self._active_runs: Dict[str, Dict[str, Any]] = {}

    # =========================================================
    # Public
    # =========================================================

    def run_task(self, task_info: Dict[str, Any]) -> Dict[str, Any]:
        last_result: Optional[Dict[str, Any]] = None

        while True:
            last_result = self.run_task_slice(task_info)
            status = str(last_result.get("status", "")).strip().lower()

            if status in {"finished", "failed", "canceled"}:
                return last_result

            if status in {"paused", "retrying", "waiting", "blocked"}:
                return last_result

    def run_task_slice(self, task_info: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(task_info, dict):
            raise TypeError("task_info must be a dict.")

        task_name = str(task_info.get("task_name", "")).strip()
        goal = str(task_info.get("goal", "")).strip()

        if not task_name:
            raise ValueError("task_info['task_name'] is required.")

        run_state = self._ensure_run_state(task_info)
        self._sync_retry_fields_from_task_info(task_info, run_state)

        task_dir = run_state["task_dir"]

        current_status = str(task_info.get("status", "")).strip().lower()
        if current_status == "paused":
            return {
                "success": True,
                "status": "paused",
                "summary": f"Task paused: {task_name}",
                "data": self._build_runtime_data(run_state),
                "error": None,
            }

        try:
            if not run_state["started"]:
                self._start_run(task_name=task_name, goal=goal, run_state=run_state)

            steps = run_state["steps"]
            next_step_index = int(run_state["next_step_index"])

            if next_step_index >= len(steps):
                final_result = self._finalize_success(task_name, goal, run_state)
                self._clear_active_run(task_name)
                return final_result

            step = steps[next_step_index]
            if not isinstance(step, dict):
                raise ValueError(
                    f"plan step must be dict, got: {type(step).__name__}"
                )

            human_step_index = next_step_index + 1

            step_result = self._execute_step(
                step_index=human_step_index,
                step=step,
                goal=goal,
                task_type=run_state["task_type"],
            )

            step_file = task_dir / f"step_{human_step_index:02d}.json"
            self._save_json(step_file, step_result)
            run_state["step_results"].append(step_result)
            run_state["next_step_index"] = next_step_index + 1

            self._append_log(
                task_dir,
                f"Step {human_step_index:02d} finished: {step_result.get('step_text', '')}",
            )

            self._raise_if_step_failed(step_result)

            self._persist_runtime_state(task_name, run_state)

            if run_state["next_step_index"] >= len(steps):
                final_result = self._finalize_success(task_name, goal, run_state)
                self._clear_active_run(task_name)
                return final_result

            return {
                "success": True,
                "status": "running",
                "summary": f"Task step executed: {task_name}",
                "data": self._build_runtime_data(run_state),
                "error": None,
            }

        except Exception as exc:
            return self._handle_task_failure(
                task_info=task_info,
                task_name=task_name,
                goal=goal,
                run_state=run_state,
                exc=exc,
            )

    def pause_task(
        self,
        task_info: Dict[str, Any],
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not isinstance(task_info, dict):
            raise TypeError("task_info must be a dict.")

        task_name = str(task_info.get("task_name", "")).strip()
        if not task_name:
            raise ValueError("task_info['task_name'] is required.")

        run_state = self._ensure_run_state(task_info)
        self._set_task_status(task_name, "paused")
        self._append_log(
            run_state["task_dir"],
            f"Task paused: {task_name}" + (f" | reason={reason}" if reason else ""),
        )
        self._persist_runtime_state(task_name, run_state, override_status="paused")

        return {
            "success": True,
            "status": "paused",
            "summary": f"Task paused: {task_name}",
            "data": self._build_runtime_data(run_state),
            "error": None,
        }

    def resume_task(self, task_info: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(task_info, dict):
            raise TypeError("task_info must be a dict.")

        task_name = str(task_info.get("task_name", "")).strip()
        if not task_name:
            raise ValueError("task_info['task_name'] is required.")

        run_state = self._ensure_run_state(task_info)
        self._set_task_status(task_name, "running")
        self._append_log(run_state["task_dir"], f"Task resumed: {task_name}")
        self._persist_runtime_state(task_name, run_state, override_status="running")

        return {
            "success": True,
            "status": "running",
            "summary": f"Task resumed: {task_name}",
            "data": self._build_runtime_data(run_state),
            "error": None,
        }

    # =========================================================
    # Run State
    # =========================================================

    def _ensure_run_state(self, task_info: Dict[str, Any]) -> Dict[str, Any]:
        task_name = str(task_info.get("task_name", "")).strip()
        if task_name in self._active_runs:
            run_state = self._active_runs[task_name]
            self._sync_retry_fields_from_task_info(task_info, run_state)
            return run_state

        task_dir = self.workspace_root / task_name
        task_dir.mkdir(parents=True, exist_ok=True)

        runtime_state_file = task_dir / "runtime_state.json"
        if runtime_state_file.exists():
            restored = self._load_runtime_state(runtime_state_file)
            if restored is not None:
                restored["task_dir"] = task_dir
                self._sync_retry_fields_from_task_info(task_info, restored)
                self._active_runs[task_name] = restored
                return restored

        run_state: Dict[str, Any] = {
            "task_name": task_name,
            "goal": str(task_info.get("goal", "")).strip(),
            "priority": self._coerce_int(task_info.get("priority"), default=0),
            "task_dir": task_dir,
            "started": False,
            "plan": None,
            "steps": [],
            "task_type": "general",
            "next_step_index": 0,
            "step_results": [],
            "retry_count": self._coerce_int(task_info.get("retry_count"), default=0),
            "max_retries": self._coerce_int(task_info.get("max_retries"), default=0),
            "retry_delay_ticks": self._coerce_int(
                task_info.get("retry_delay_ticks"),
                default=0,
            ),
            "next_retry_tick": self._coerce_int(
                task_info.get("next_retry_tick"),
                default=0,
            ),
            "last_error": task_info.get("last_error"),
        }
        self._active_runs[task_name] = run_state
        return run_state

    def _load_runtime_state(self, runtime_state_file: Path) -> Optional[Dict[str, Any]]:
        try:
            with open(runtime_state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None

        if not isinstance(data, dict):
            return None

        return {
            "task_name": str(data.get("task_name", "")).strip(),
            "goal": str(data.get("goal", "")).strip(),
            "priority": self._coerce_int(data.get("priority"), default=0),
            "task_dir": runtime_state_file.parent,
            "started": bool(data.get("started", False)),
            "plan": data.get("plan"),
            "steps": data.get("steps", []) if isinstance(data.get("steps"), list) else [],
            "task_type": str(data.get("task_type", "general")).strip() or "general",
            "next_step_index": self._coerce_int(data.get("next_step_index"), default=0),
            "step_results": (
                data.get("step_results", [])
                if isinstance(data.get("step_results"), list)
                else []
            ),
            "retry_count": self._coerce_int(data.get("retry_count"), default=0),
            "max_retries": self._coerce_int(data.get("max_retries"), default=0),
            "retry_delay_ticks": self._coerce_int(
                data.get("retry_delay_ticks"),
                default=0,
            ),
            "next_retry_tick": self._coerce_int(
                data.get("next_retry_tick"),
                default=0,
            ),
            "last_error": data.get("last_error"),
        }

    def _persist_runtime_state(
        self,
        task_name: str,
        run_state: Dict[str, Any],
        override_status: Optional[str] = None,
    ) -> None:
        status = override_status or self._get_task_status(task_name) or "created"

        payload = {
            "task_name": task_name,
            "goal": run_state.get("goal", ""),
            "priority": run_state.get("priority", 0),
            "started": bool(run_state.get("started", False)),
            "task_type": run_state.get("task_type", "general"),
            "next_step_index": int(run_state.get("next_step_index", 0)),
            "step_count_completed": len(run_state.get("step_results", [])),
            "status": str(status),
            "plan": run_state.get("plan"),
            "steps": run_state.get("steps", []),
            "step_results": run_state.get("step_results", []),
            "retry_count": self._coerce_int(run_state.get("retry_count"), default=0),
            "max_retries": self._coerce_int(run_state.get("max_retries"), default=0),
            "retry_delay_ticks": self._coerce_int(
                run_state.get("retry_delay_ticks"),
                default=0,
            ),
            "next_retry_tick": self._coerce_int(
                run_state.get("next_retry_tick"),
                default=0,
            ),
            "last_error": run_state.get("last_error"),
        }

        self._save_json(run_state["task_dir"] / "runtime_state.json", payload)

    def _clear_active_run(self, task_name: str) -> None:
        self._active_runs.pop(task_name, None)

    # =========================================================
    # Start / Finish
    # =========================================================

    def _start_run(
        self,
        task_name: str,
        goal: str,
        run_state: Dict[str, Any],
    ) -> None:
        plan = self._create_dynamic_plan(goal)
        steps = plan.get("steps", [])
        if not isinstance(steps, list):
            raise ValueError("plan['steps'] must be a list.")

        run_state["started"] = True
        run_state["plan"] = plan
        run_state["steps"] = steps
        run_state["task_type"] = str(plan.get("task_type", "general")).strip() or "general"
        run_state["next_step_index"] = 0
        run_state["step_results"] = []

        self._set_task_status(task_name, "running")
        self._append_log(run_state["task_dir"], f"Task started: {task_name}")
        self._append_log(run_state["task_dir"], f"Goal: {goal}")
        self._append_log(run_state["task_dir"], "Status changed to: running")

        self._save_json(run_state["task_dir"] / "plan.json", plan)
        self._persist_runtime_state(task_name, run_state)

    def _finalize_success(
        self,
        task_name: str,
        goal: str,
        run_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        task_dir = run_state["task_dir"]

        result = self._build_final_result(
            task_name=task_name,
            goal=goal,
            task_type=run_state["task_type"],
            step_results=run_state["step_results"],
        )
        self._save_json(task_dir / "result.json", result)

        self._append_log(task_dir, "Task finished.")
        self._set_task_status(task_name, "finished")
        self._persist_runtime_state(task_name, run_state, override_status="finished")

        step_files = [
            str(task_dir / f"step_{i:02d}.json")
            for i in range(1, len(run_state["step_results"]) + 1)
        ]

        tool_summary = self._build_tool_execution_summary(run_state["step_results"])

        return {
            "success": True,
            "status": "finished",
            "summary": f"Task finished: {task_name}",
            "data": {
                "task_name": task_name,
                "task_dir": str(task_dir),
                "status": "finished",
                "task_type": run_state["task_type"],
                "planner_version": run_state["plan"].get("planner_version", "unknown"),
                "plan_file": str(task_dir / "plan.json"),
                "runtime_state_file": str(task_dir / "runtime_state.json"),
                "step_files": step_files,
                "result_file": str(task_dir / "result.json"),
                "log_file": str(task_dir / "log.txt"),
                "step_count": len(run_state["step_results"]),
                "tools_used": tool_summary["tools_used"],
                "tool_step_count": tool_summary["tool_step_count"],
                "tool_success_count": tool_summary["tool_success_count"],
                "tool_failure_count": tool_summary["tool_failure_count"],
                "all_tool_steps_succeeded": tool_summary["all_tool_steps_succeeded"],
            },
            "error": None,
        }

    def _build_runtime_data(self, run_state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "task_name": run_state["task_name"],
            "task_dir": str(run_state["task_dir"]),
            "task_type": run_state["task_type"],
            "next_step_index": int(run_state["next_step_index"]),
            "step_count_completed": len(run_state["step_results"]),
            "total_step_count": len(run_state["steps"]),
            "retry_count": self._coerce_int(run_state.get("retry_count"), default=0),
            "max_retries": self._coerce_int(run_state.get("max_retries"), default=0),
            "retry_delay_ticks": self._coerce_int(
                run_state.get("retry_delay_ticks"),
                default=0,
            ),
            "next_retry_tick": self._coerce_int(
                run_state.get("next_retry_tick"),
                default=0,
            ),
            "last_error": run_state.get("last_error"),
            "runtime_state_file": str(run_state["task_dir"] / "runtime_state.json"),
            "plan_file": str(run_state["task_dir"] / "plan.json"),
            "log_file": str(run_state["task_dir"] / "log.txt"),
        }

    # =========================================================
    # Dynamic Planning
    # =========================================================

    def _create_dynamic_plan(self, goal: str) -> Dict[str, Any]:
        goal_text = str(goal).strip()
        task_type = self._classify_task_type(goal_text)

        if task_type == "workspace_read":
            target_path = self._extract_ws_target(goal_text)
            steps = [
                {"name": "analyze workspace file task", "kind": "reason"},
                {
                    "name": "read file with workspace tool",
                    "kind": "tool",
                    "tool_name": "workspace_tool",
                    "tool_args": {
                        "action": "read_file",
                        "path": target_path,
                    },
                },
                {"name": "summarize file handling", "kind": "reason"},
                {"name": "save result", "kind": "reason"},
            ]

        elif task_type == "command":
            command_text = self._extract_command_from_goal(goal_text)
            steps = [
                {"name": "analyze command intent", "kind": "reason"},
                {
                    "name": "execute command tool",
                    "kind": "tool",
                    "tool_name": "command_tool",
                    "tool_args": {
                        "command": command_text,
                    },
                },
                {"name": "collect command result", "kind": "reason"},
                {"name": "save result", "kind": "reason"},
            ]

        elif task_type == "file":
            target_path = self._extract_file_target(goal_text)
            steps = [
                {"name": "analyze file task", "kind": "reason"},
                {
                    "name": "read file with workspace tool",
                    "kind": "tool",
                    "tool_name": "workspace_tool",
                    "tool_args": {
                        "action": "read_file",
                        "path": target_path,
                    },
                },
                {"name": "summarize file handling", "kind": "reason"},
                {"name": "save result", "kind": "reason"},
            ]

        else:
            steps = [
                {"name": "analyze goal", "kind": "reason"},
                {"name": "plan response", "kind": "reason"},
                {"name": "summarize outcome", "kind": "reason"},
                {"name": "save result", "kind": "reason"},
            ]

        return {
            "goal": goal_text,
            "task_type": task_type,
            "planner_version": "tool_aware_rules_v4_retry_real",
            "steps": steps,
        }

    def _classify_task_type(self, goal: str) -> str:
        lowered = goal.lower().strip()

        if lowered.startswith("ws:"):
            return "workspace_read"

        if lowered.startswith("cmd:"):
            return "command"

        command_keywords = [
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

        if task_type == "command":
            return self._execute_command_reason_step(normalized_step, step_text, goal)

        if task_type in {"file", "workspace_read"}:
            return self._execute_file_reason_step(normalized_step, step_text, goal)

        return self._execute_general_reason_step(normalized_step, step_text, goal)

    def _execute_command_reason_step(
        self,
        normalized_step: str,
        step_text: str,
        goal: str,
    ) -> Dict[str, Any]:
        if normalized_step == "analyze command intent":
            return {
                "goal": goal,
                "analysis": "Detected command-oriented task.",
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
        if normalized_step in {"analyze file task", "analyze workspace file task"}:
            return {
                "goal": goal,
                "analysis": "Detected file-oriented task.",
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
                "plan": "Response plan created (tool-aware rules v4 retry real).",
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

    def _handle_task_failure(
        self,
        task_info: Dict[str, Any],
        task_name: str,
        goal: str,
        run_state: Dict[str, Any],
        exc: Exception,
    ) -> Dict[str, Any]:
        task_dir = run_state["task_dir"]
        error_text = str(exc).strip() or exc.__class__.__name__

        self._append_log(task_dir, f"Task failed: {error_text}")
        run_state["last_error"] = error_text

        self._rollback_failed_step(run_state)

        retry_count = self._coerce_int(
            task_info.get("retry_count", run_state.get("retry_count", 0)),
            default=self._coerce_int(run_state.get("retry_count"), default=0),
        )
        max_retries = self._coerce_int(
            task_info.get("max_retries", run_state.get("max_retries", 0)),
            default=self._coerce_int(run_state.get("max_retries"), default=0),
        )
        retry_delay_ticks = self._coerce_int(
            task_info.get("retry_delay_ticks", run_state.get("retry_delay_ticks", 0)),
            default=self._coerce_int(run_state.get("retry_delay_ticks"), default=0),
        )

        run_state["retry_count"] = retry_count
        run_state["max_retries"] = max_retries
        run_state["retry_delay_ticks"] = retry_delay_ticks

        if retry_count < max_retries:
            next_retry_count = retry_count + 1
            current_tick = self._get_current_tick(task_info)
            next_retry_tick = current_tick + max(retry_delay_ticks, 0)

            run_state["retry_count"] = next_retry_count
            run_state["next_retry_tick"] = next_retry_tick
            run_state["last_error"] = error_text

            self._set_task_retry_state(
                task_name=task_name,
                retry_count=next_retry_count,
                next_retry_tick=next_retry_tick,
                last_error=error_text,
                status="retrying",
            )

            self._append_log(
                task_dir,
                (
                    "Task scheduled for retry: "
                    f"task={task_name}, retry_count={next_retry_count}, "
                    f"max_retries={max_retries}, next_retry_tick={next_retry_tick}"
                ),
            )

            retry_result = {
                "task_name": task_name,
                "goal": goal,
                "status": "retrying",
                "message": error_text,
                "retry_count": next_retry_count,
                "max_retries": max_retries,
                "retry_delay_ticks": retry_delay_ticks,
                "next_retry_tick": next_retry_tick,
                "next_step_index": run_state.get("next_step_index", 0),
                "step_count_completed": len(run_state.get("step_results", [])),
            }

            self._save_json(task_dir / "result.json", retry_result)
            self._persist_runtime_state(task_name, run_state, override_status="retrying")
            self._clear_active_run(task_name)

            return {
                "success": False,
                "status": "retrying",
                "summary": f"Task scheduled for retry: {task_name}",
                "data": {
                    "task_name": task_name,
                    "task_dir": str(task_dir),
                    "status": "retrying",
                    "retry_count": next_retry_count,
                    "max_retries": max_retries,
                    "retry_delay_ticks": retry_delay_ticks,
                    "next_retry_tick": next_retry_tick,
                    "result_file": str(task_dir / "result.json"),
                    "runtime_state_file": str(task_dir / "runtime_state.json"),
                    "log_file": str(task_dir / "log.txt"),
                },
                "error": error_text,
            }

        run_state["next_retry_tick"] = self._coerce_int(
            run_state.get("next_retry_tick"),
            default=0,
        )

        self._set_task_retry_state(
            task_name=task_name,
            retry_count=retry_count,
            next_retry_tick=run_state["next_retry_tick"],
            last_error=error_text,
            status="failed",
        )

        failed_result = {
            "task_name": task_name,
            "goal": goal,
            "status": "failed",
            "message": error_text,
            "retry_count": retry_count,
            "max_retries": max_retries,
            "retry_delay_ticks": retry_delay_ticks,
            "next_retry_tick": run_state.get("next_retry_tick", 0),
            "next_step_index": run_state.get("next_step_index", 0),
            "step_count_completed": len(run_state.get("step_results", [])),
        }

        self._save_json(task_dir / "result.json", failed_result)
        self._persist_runtime_state(task_name, run_state, override_status="failed")
        self._clear_active_run(task_name)

        return {
            "success": False,
            "status": "failed",
            "summary": f"Task failed: {task_name}",
            "data": {
                "task_name": task_name,
                "task_dir": str(task_dir),
                "status": "failed",
                "retry_count": retry_count,
                "max_retries": max_retries,
                "retry_delay_ticks": retry_delay_ticks,
                "next_retry_tick": run_state.get("next_retry_tick", 0),
                "result_file": str(task_dir / "result.json"),
                "runtime_state_file": str(task_dir / "runtime_state.json"),
                "log_file": str(task_dir / "log.txt"),
            },
            "error": error_text,
        }

    def _rollback_failed_step(self, run_state: Dict[str, Any]) -> None:
        next_step_index = self._coerce_int(run_state.get("next_step_index"), default=0)
        step_results = run_state.get("step_results", [])

        if next_step_index > 0:
            run_state["next_step_index"] = next_step_index - 1

        if isinstance(step_results, list) and step_results:
            last_item = step_results[-1]
            if isinstance(last_item, dict):
                last_status = str(last_item.get("status", "")).strip().lower()
                if last_status == "failed":
                    step_results.pop()

    # =========================================================
    # Final Result
    # =========================================================

    def _build_final_result(
        self,
        task_name: str,
        goal: str,
        task_type: str,
        step_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        tool_summary = self._build_tool_execution_summary(step_results)

        return {
            "task_name": task_name,
            "goal": goal,
            "task_type": task_type,
            "status": "finished",
            "message": "Task finished (tool-aware runtime, retry-safe)",
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

        if hasattr(self.tool_registry, "get_tool"):
            tool = self.tool_registry.get_tool(clean_name)
            if tool is not None:
                return tool

        if hasattr(self.tool_registry, "tools"):
            tools = getattr(self.tool_registry, "tools")
            if isinstance(tools, dict):
                return tools.get(clean_name)

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

    def _extract_ws_target(self, goal: str) -> str:
        text = str(goal).strip()
        if text.lower().startswith("ws:"):
            return text[3:].strip()
        return text

    def _extract_command_from_goal(self, goal: str) -> str:
        text = str(goal).strip()

        prefixes = [
            "execute command ",
            "run command ",
            "cmd:",
            "執行指令 ",
            "執行命令 ",
        ]

        lowered = text.lower()
        for prefix in prefixes:
            if lowered.startswith(prefix):
                return text[len(prefix):].strip() or "echo placeholder"

        return text

    def _extract_file_target(self, goal: str) -> str:
        tokens = str(goal).replace("\\", " \\ ").replace("/", " / ").split()

        for token in tokens:
            clean = token.strip().strip("\"'")

            if clean.endswith((".py", ".json", ".txt", ".md")):
                return clean

        return "task_memory.json"

    # =========================================================
    # Retry / Task Manager Helpers
    # =========================================================

    def _sync_retry_fields_from_task_info(
        self,
        task_info: Dict[str, Any],
        run_state: Dict[str, Any],
    ) -> None:
        if not isinstance(task_info, dict):
            return

        for key in (
            "retry_count",
            "max_retries",
            "retry_delay_ticks",
            "next_retry_tick",
        ):
            if key in task_info:
                run_state[key] = self._coerce_int(
                    task_info.get(key),
                    default=self._coerce_int(run_state.get(key), default=0),
                )

        if "last_error" in task_info:
            run_state["last_error"] = task_info.get("last_error")

    def _get_current_tick(self, task_info: Dict[str, Any]) -> int:
        candidates = [
            task_info.get("current_tick"),
            task_info.get("tick"),
        ]

        if self.task_manager is not None:
            candidates.extend(
                [
                    getattr(self.task_manager, "current_tick", None),
                    getattr(self.task_manager, "tick", None),
                ]
            )

        for value in candidates:
            try:
                if value is not None:
                    return int(value)
            except Exception:
                continue

        return 0

    def _set_task_retry_state(
        self,
        task_name: str,
        retry_count: int,
        next_retry_tick: int,
        last_error: Optional[str],
        status: str,
    ) -> None:
        self._update_task_field(task_name, "retry_count", retry_count)
        self._update_task_field(task_name, "next_retry_tick", next_retry_tick)
        self._update_task_field(task_name, "last_error", last_error)
        self._set_task_status(task_name, status)

    def _update_task_field(self, task_name: str, field_name: str, value: Any) -> None:
        if self.task_manager is None:
            return

        method_names = [
            "update_task_field",
            "set_task_field",
        ]

        for method_name in method_names:
            method = getattr(self.task_manager, method_name, None)
            if callable(method):
                try:
                    method(task_name, field_name, value)
                    return
                except Exception:
                    pass

        update_task_method = getattr(self.task_manager, "update_task", None)
        if callable(update_task_method):
            try:
                update_task_method(task_name, {field_name: value})
                return
            except Exception:
                pass

        get_task_method = getattr(self.task_manager, "get_task", None)
        if callable(get_task_method):
            try:
                task = get_task_method(task_name)
                if isinstance(task, dict):
                    task[field_name] = value
                    upsert_method = getattr(self.task_manager, "upsert_task", None)
                    if callable(upsert_method):
                        upsert_method(task)
                    return
            except Exception:
                pass

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
            except Exception:
                pass

    def _get_task_status(self, task_name: str) -> Optional[str]:
        if self.task_manager is None:
            return None

        get_task_method = getattr(self.task_manager, "get_task", None)
        if not callable(get_task_method):
            return None

        try:
            task = get_task_method(task_name)
        except Exception:
            return None

        if isinstance(task, dict):
            status = task.get("status")
            if status is not None:
                return str(status)

        return None

    def _normalize_tool_name(self, value: Any) -> Optional[str]:
        if value is None:
            return None

        text = str(value).strip()
        if not text:
            return None

        if text.lower() == "none":
            return None

        return text

    def _coerce_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default

    def _save_json(self, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _append_log(self, task_dir: Path, text: str) -> None:
        task_dir.mkdir(parents=True, exist_ok=True)
        log_file = task_dir / "log.txt"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(text + "\n")