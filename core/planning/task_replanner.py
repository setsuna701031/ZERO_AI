from __future__ import annotations

import copy
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.planning.planner import Planner


class TaskReplanner:
    """
    Runtime Task Replanner

    用途：
    - 給目前這套 Task OS / Scheduler / TaskRunner 使用
    - 當 step 失敗且決定 replan 時：
      1. 重建 plan.json
      2. 重置 runtime_state.json
      3. 累加 replan_count
      4. 寫入 replan_log.json

    設計重點：
    - 不硬依賴 Planner 一定有 build_and_save_plan
    - 會自動偵測 Planner 可用的方法
    - 如果 Planner 方法不存在，就使用內建 fallback planner
    """

    def __init__(self, workspace_dir: str = "workspace") -> None:
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.planner = Planner(workspace_dir=self.workspace_dir)

    # =========================================================
    # Public API
    # =========================================================

    def replan(
        self,
        *,
        goal: str,
        task_dir: str,
        plan_file: Optional[str] = None,
        runtime_file: Optional[str] = None,
        reason: str = "",
        failed_step: Optional[Dict[str, Any]] = None,
        preserve_history: bool = True,
    ) -> Dict[str, Any]:
        """
        重新規劃任務，重建 plan.json，並重置 runtime_state.json
        """
        try:
            task_dir = os.path.abspath(task_dir)
            plan_file = plan_file or os.path.join(task_dir, "plan.json")
            runtime_file = runtime_file or os.path.join(task_dir, "runtime_state.json")

            old_runtime = self._read_json(runtime_file, default={})
            old_history = old_runtime.get("step_history", []) if isinstance(old_runtime, dict) else []
            old_replan_count = int(old_runtime.get("replan_count", 0) or 0) if isinstance(old_runtime, dict) else 0
            old_max_replans = int(old_runtime.get("max_replans", 1) or 1) if isinstance(old_runtime, dict) else 1
            old_execution_log = old_runtime.get("execution_log", []) if isinstance(old_runtime, dict) else []
            old_goal = ""
            old_title = ""

            if isinstance(old_runtime, dict):
                old_goal = str(old_runtime.get("goal", "") or "")
                old_title = str(old_runtime.get("title", "") or "")

            final_goal = str(goal or old_goal or old_title or "").strip()
            if not final_goal:
                return {
                    "ok": False,
                    "replanned": False,
                    "reason": reason,
                    "step_count": 0,
                    "plan_file": plan_file,
                    "runtime_file": runtime_file,
                    "error": "goal is empty",
                }

            planner_result = self._generate_plan_result(
                goal=final_goal,
                task_dir=task_dir,
                plan_file=plan_file,
            )

            steps = planner_result.get("steps", [])
            if not isinstance(steps, list):
                steps = []

            self._save_json(plan_file, planner_result)

            runtime_state = self._default_runtime_state()
            runtime_state["task_name"] = str(old_runtime.get("task_name", "") or os.path.basename(task_dir))
            runtime_state["status"] = "ready"
            runtime_state["current_step_index"] = 0
            runtime_state["steps_total"] = len(steps)
            runtime_state["steps"] = copy.deepcopy(steps)
            runtime_state["results"] = []
            runtime_state["step_results"] = []
            runtime_state["last_step_result"] = None
            runtime_state["replanned"] = True
            runtime_state["replan_reason"] = reason or ""
            runtime_state["replan_count"] = old_replan_count + 1
            runtime_state["max_replans"] = old_max_replans
            runtime_state["planner_result"] = copy.deepcopy(planner_result)
            runtime_state["goal"] = final_goal
            runtime_state["title"] = final_goal
            runtime_state["task_dir"] = task_dir
            runtime_state["workspace_dir"] = os.path.dirname(task_dir)
            runtime_state["plan_file"] = plan_file
            runtime_state["runtime_state_file"] = runtime_file
            runtime_state["execution_log_file"] = os.path.join(task_dir, "execution_log.json")
            runtime_state["result_file"] = os.path.join(task_dir, "result.json")
            runtime_state["log_file"] = os.path.join(task_dir, "task.log")
            runtime_state["failure_type"] = None
            runtime_state["failure_message"] = None
            runtime_state["last_error"] = None
            runtime_state["blocked_reason"] = ""

            if preserve_history and isinstance(old_history, list):
                runtime_state["step_history"] = copy.deepcopy(old_history)
            else:
                runtime_state["step_history"] = []

            runtime_state["step_history"].append(
                {
                    "event": "replan",
                    "reason": reason or "",
                    "failed_step": failed_step,
                    "at": self._now_iso(),
                }
            )

            if isinstance(old_execution_log, list):
                runtime_state["execution_log"] = copy.deepcopy(old_execution_log)
            else:
                runtime_state["execution_log"] = []

            runtime_state["execution_log"].append(
                {
                    "type": "replan",
                    "reason": reason or "",
                    "failed_step": failed_step,
                    "replan_count": runtime_state["replan_count"],
                    "steps_total": len(steps),
                    "at": self._now_iso(),
                }
            )

            self._save_json(runtime_file, runtime_state)
            self._save_json(runtime_state["execution_log_file"], runtime_state["execution_log"])

            self._append_replan_log(
                task_dir=task_dir,
                reason=reason,
                failed_step=failed_step,
                new_step_count=len(steps),
                replan_count=runtime_state["replan_count"],
            )

            return {
                "ok": True,
                "replanned": True,
                "reason": reason,
                "step_count": len(steps),
                "plan_file": plan_file,
                "runtime_file": runtime_file,
                "error": None,
            }

        except Exception as e:
            return {
                "ok": False,
                "replanned": False,
                "reason": reason,
                "step_count": 0,
                "plan_file": plan_file or "",
                "runtime_file": runtime_file or "",
                "error": str(e),
            }

    # =========================================================
    # Planner adapters
    # =========================================================

    def _generate_plan_result(
        self,
        *,
        goal: str,
        task_dir: str,
        plan_file: str,
    ) -> Dict[str, Any]:
        """
        盡量相容不同 Planner API：
        1. build_and_save_plan
        2. build_plan
        3. plan
        4. fallback deterministic
        """
        # 1) 新版：build_and_save_plan
        build_and_save = getattr(self.planner, "build_and_save_plan", None)
        if callable(build_and_save):
            steps = build_and_save(
                goal=goal,
                task_dir=task_dir,
                plan_file=plan_file,
            )
            if not isinstance(steps, list):
                steps = []
            return self._wrap_plan_result(goal=goal, steps=steps, planner_mode="planner.build_and_save_plan")

        # 2) build_plan
        build_plan = getattr(self.planner, "build_plan", None)
        if callable(build_plan):
            result = build_plan(goal=goal, task_dir=task_dir)
            normalized = self._normalize_planner_output(goal=goal, result=result, planner_mode="planner.build_plan")
            return normalized

        # 3) plan
        plan_fn = getattr(self.planner, "plan", None)
        if callable(plan_fn):
            result = plan_fn(goal=goal, task_dir=task_dir)
            normalized = self._normalize_planner_output(goal=goal, result=result, planner_mode="planner.plan")
            return normalized

        # 4) fallback deterministic
        return self._fallback_plan(goal)

    def _normalize_planner_output(
        self,
        *,
        goal: str,
        result: Any,
        planner_mode: str,
    ) -> Dict[str, Any]:
        if isinstance(result, dict):
            steps = result.get("steps", [])
            if not isinstance(steps, list):
                steps = []
            normalized = copy.deepcopy(result)
            normalized["steps"] = steps
            normalized.setdefault("planner_mode", planner_mode)
            normalized.setdefault("final_answer", f"已規劃 {len(steps)} 個步驟")
            return normalized

        if isinstance(result, list):
            return self._wrap_plan_result(goal=goal, steps=result, planner_mode=planner_mode)

        return self._fallback_plan(goal)

    def _wrap_plan_result(self, *, goal: str, steps: List[Dict[str, Any]], planner_mode: str) -> Dict[str, Any]:
        intent = self._infer_intent(goal, steps)
        return {
            "planner_mode": planner_mode,
            "intent": intent,
            "final_answer": f"已規劃 {len(steps)} 個步驟",
            "steps": copy.deepcopy(steps),
        }

    def _fallback_plan(self, goal: str) -> Dict[str, Any]:
        text = goal.strip()
        lowered = text.lower()

        if lowered.startswith("cmd:"):
            command = text[4:].strip()
            return {
                "planner_mode": "task_replanner_fallback",
                "intent": "command",
                "final_answer": "已規劃 1 個步驟",
                "steps": [
                    {
                        "type": "command",
                        "command": command,
                    }
                ],
            }

        if self._looks_like_hello_world_python(text):
            return {
                "planner_mode": "task_replanner_fallback",
                "intent": "python_hello_world",
                "final_answer": "已規劃 2 個步驟",
                "steps": [
                    {
                        "type": "write_file",
                        "path": "hello.py",
                        "content": 'print("hello world")\n',
                    },
                    {
                        "type": "command",
                        "command": "python hello.py",
                    },
                ],
            }

        write_file_step = self._try_plan_write_file(text)
        if write_file_step is not None:
            return {
                "planner_mode": "task_replanner_fallback",
                "intent": "write_file",
                "final_answer": "已規劃 1 個步驟",
                "steps": [write_file_step],
            }

        read_file_step = self._try_plan_read_file(text)
        if read_file_step is not None:
            return {
                "planner_mode": "task_replanner_fallback",
                "intent": "read_file",
                "final_answer": "已規劃 1 個步驟",
                "steps": [read_file_step],
            }

        command_step = self._try_plan_command(text)
        if command_step is not None:
            return {
                "planner_mode": "task_replanner_fallback",
                "intent": "command",
                "final_answer": "已規劃 1 個步驟",
                "steps": [command_step],
            }

        return {
            "planner_mode": "task_replanner_fallback",
            "intent": "unresolved",
            "final_answer": "目前 fallback planner 還無法把這個 goal 轉成可執行 steps。",
            "steps": [],
        }

    # =========================================================
    # Fallback deterministic helpers
    # =========================================================

    def _infer_intent(self, goal: str, steps: List[Dict[str, Any]]) -> str:
        if not steps:
            return "unresolved"
        first = steps[0]
        if isinstance(first, dict):
            return str(first.get("type") or first.get("intent") or "unknown")
        return "unknown"

    def _looks_like_hello_world_python(self, text: str) -> bool:
        lowered = text.lower()
        candidates = [
            "hello world python",
            "hello world 的 python",
            "寫一個 hello world python",
            "建立 hello world python",
            "做一個 hello world python",
            "python hello world",
        ]
        return any(item in lowered for item in candidates)

    def _try_plan_command(self, text: str) -> Optional[Dict[str, Any]]:
        lowered = text.lower().strip()

        command_prefixes = [
            "run ",
            "execute ",
            "cmd ",
            "cmd /c ",
            "powershell ",
            "執行 ",
            "跑 ",
            "命令 ",
            "指令 ",
        ]

        for prefix in command_prefixes:
            if lowered.startswith(prefix):
                command = text[len(prefix):].strip()
                if command:
                    return {
                        "type": "command",
                        "command": command,
                    }

        return None

    def _try_plan_read_file(self, text: str) -> Optional[Dict[str, Any]]:
        import re

        lowered = text.lower()
        path_match = re.search(r"([A-Za-z0-9_\-./\\]+\.(py|txt|md|json|yaml|yml|csv))", text)
        if not path_match:
            return None

        if any(keyword in lowered for keyword in ["讀取", "讀檔", "read ", "open ", "查看", "看一下", "show "]):
            return {
                "type": "read_file",
                "path": path_match.group(1),
            }

        return None

    def _try_plan_write_file(self, text: str) -> Optional[Dict[str, Any]]:
        import re

        path_match = re.search(r"([A-Za-z0-9_\-./\\]+\.(py|txt|md|json|yaml|yml|csv))", text)
        if not path_match:
            return None

        path = path_match.group(1)

        content_match = re.search(r"(?:內容是|內容為|內容:|內容：)(.+)$", text)
        if content_match:
            content = content_match.group(1).strip()
            return {
                "type": "write_file",
                "path": path,
                "content": self._normalize_inline_content(content),
            }

        content_match = re.search(r"(?:content is|content:)(.+)$", text, flags=re.IGNORECASE)
        if content_match:
            content = content_match.group(1).strip()
            return {
                "type": "write_file",
                "path": path,
                "content": self._normalize_inline_content(content),
            }

        lowered = text.lower()
        if any(keyword in lowered for keyword in ["建立", "新增", "create", "write"]):
            default_content = self._default_file_content(path, text)
            return {
                "type": "write_file",
                "path": path,
                "content": default_content,
            }

        return None

    def _default_file_content(self, path: str, goal: str) -> str:
        lowered_path = path.lower()

        if lowered_path.endswith(".py"):
            if "hello" in goal.lower():
                return 'print("hello world")\n'
            return "# generated by ZERO\n"

        if lowered_path.endswith(".md"):
            return "# generated by ZERO\n"

        if lowered_path.endswith(".json"):
            return "{}\n"

        return ""

    def _normalize_inline_content(self, content: str) -> str:
        content = content.strip()

        if (
            (content.startswith('"') and content.endswith('"'))
            or (content.startswith("'") and content.endswith("'"))
        ):
            content = content[1:-1]

        content = content.replace("\\n", "\n")
        if not content.endswith("\n"):
            content += "\n"
        return content

    # =========================================================
    # Helpers
    # =========================================================

    def _default_runtime_state(self) -> Dict[str, Any]:
        return {
            "task_name": "",
            "status": "ready",
            "priority": 0,
            "retry_count": 0,
            "max_retries": 0,
            "retry_delay": 0,
            "next_retry_tick": 0,
            "timeout_ticks": 0,
            "wait_until_tick": 0,
            "created_tick": 0,
            "last_run_tick": None,
            "last_failure_tick": None,
            "finished_tick": None,
            "depends_on": [],
            "blocked_reason": "",
            "failure_type": None,
            "failure_message": None,
            "last_error": None,
            "final_answer": "",
            "cancel_requested": False,
            "cancel_reason": "",
            "runtime_state_file": "",
            "plan_file": "",
            "log_file": "",
            "result_file": "",
            "execution_log_file": "",
            "current_step_index": 0,
            "steps_total": 0,
            "steps": [],
            "results": [],
            "step_results": [],
            "last_step_result": None,
            "replan_count": 0,
            "replanned": False,
            "replan_reason": "",
            "max_replans": 1,
            "planner_result": {},
            "history": ["queued"],
            "execution_log": [],
            "goal": "",
            "title": "",
            "task_dir": "",
            "workspace_dir": "",
            "step_history": [],
        }

    def _append_replan_log(
        self,
        *,
        task_dir: str,
        reason: str,
        failed_step: Optional[Dict[str, Any]],
        new_step_count: int,
        replan_count: int,
    ) -> None:
        log_file = os.path.join(task_dir, "replan_log.json")

        existing = self._read_json(log_file, default=[])
        if not isinstance(existing, list):
            existing = []

        existing.append(
            {
                "at": self._now_iso(),
                "reason": reason or "",
                "failed_step": failed_step,
                "new_step_count": new_step_count,
                "replan_count": replan_count,
            }
        )

        self._save_json(log_file, existing)

    def _read_json(self, file_path: str, default: Any) -> Any:
        if not os.path.exists(file_path):
            return default

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _save_json(self, file_path: str, data: Any) -> None:
        parent = os.path.dirname(file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _now_iso(self) -> str:
        return datetime.now().isoformat(timespec="seconds")