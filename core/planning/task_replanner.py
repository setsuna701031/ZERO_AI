from __future__ import annotations

import copy
import hashlib
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.planning.planner import Planner


class TaskReplanner:
    """
    Runtime Task Replanner

    用途：
    - 給目前這套 Task OS / Scheduler / TaskRunner 使用
    - 當 step 失敗且決定 replan 時：
      1. 重建 plan.json
      2. 重建 runtime_state.json
      3. 累加 replan_count
      4. 寫入 replan_log.json
      5. 盡量保留已完成 steps，避免 replan 後全部重跑

    本版新增重點：
    - replan 時自動補齊 step metadata
    - 依 step_key / step signature 對齊舊步驟
    - 已成功且可保留的步驟直接標成 completed
    - current_step_index 指到第一個未完成 step

    本版修正：
    - 優先使用外部注入的 planner，避免重複建立第二個 Planner
    - 只有在外部沒有傳 planner 時，才 fallback 自建 Planner
    """

    READ_ONLY_STEP_TYPES = {
        "read_file",
        "list_files",
        "inspect",
        "analyze",
        "search",
        "web_search",
        "check",
        "verify",
        "noop",
    }

    SIDE_EFFECT_STEP_TYPES = {
        "command",
        "write_file",
        "delete_file",
        "call_api",
        "http_request",
        "shell",
        "execute",
    }

    def __init__(
        self,
        workspace_dir: str = "workspace",
        planner: Optional[Any] = None,
    ) -> None:
        self.workspace_dir = os.path.abspath(workspace_dir)

        # 優先吃外部注入，避免 system_boot 已建過 planner 時又再建一次
        if planner is not None:
            self.planner = planner
        else:
            self.planner = Planner(workspace_root=self.workspace_dir)

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
            if not isinstance(old_runtime, dict):
                old_runtime = {}

            old_history = old_runtime.get("step_history", [])
            if not isinstance(old_history, list):
                old_history = []

            old_execution_log = old_runtime.get("execution_log", [])
            if not isinstance(old_execution_log, list):
                old_execution_log = []

            old_results = old_runtime.get("results", [])
            if not isinstance(old_results, list):
                old_results = []

            old_step_results = old_runtime.get("step_results", [])
            if not isinstance(old_step_results, list):
                old_step_results = []

            old_steps = old_runtime.get("steps", [])
            if not isinstance(old_steps, list):
                old_steps = []

            old_replan_count = int(old_runtime.get("replan_count", 0) or 0)
            old_max_replans = int(old_runtime.get("max_replans", 1) or 1)
            old_goal = str(old_runtime.get("goal", "") or "")
            old_title = str(old_runtime.get("title", "") or "")
            task_name = str(old_runtime.get("task_name", "") or os.path.basename(task_dir))

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

            raw_steps = planner_result.get("steps", [])
            if not isinstance(raw_steps, list):
                raw_steps = []

            new_steps = self._normalize_steps(
                steps=raw_steps,
                task_name=task_name,
            )

            completed_registry = self._build_completed_step_registry(
                old_steps=old_steps,
                old_results=old_results,
                old_step_results=old_step_results,
            )

            merged_steps, preserved_results, first_pending_index = self._merge_completed_steps_into_new_plan(
                new_steps=new_steps,
                completed_registry=completed_registry,
            )

            normalized_plan_result = copy.deepcopy(planner_result)
            normalized_plan_result["steps"] = copy.deepcopy(merged_steps)
            normalized_plan_result.setdefault("planner_mode", "task_replanner")
            normalized_plan_result.setdefault("final_answer", f"已規劃 {len(merged_steps)} 個步驟")

            self._save_json(plan_file, normalized_plan_result)

            runtime_state = self._default_runtime_state()
            runtime_state["task_name"] = task_name
            runtime_state["status"] = "ready"
            runtime_state["current_step_index"] = first_pending_index
            runtime_state["steps_total"] = len(merged_steps)
            runtime_state["steps"] = copy.deepcopy(merged_steps)
            runtime_state["results"] = copy.deepcopy(preserved_results)
            runtime_state["step_results"] = copy.deepcopy(preserved_results)
            runtime_state["last_step_result"] = copy.deepcopy(preserved_results[-1]) if preserved_results else None
            runtime_state["replanned"] = True
            runtime_state["replan_reason"] = reason or ""
            runtime_state["replan_count"] = old_replan_count + 1
            runtime_state["max_replans"] = old_max_replans
            runtime_state["planner_result"] = copy.deepcopy(normalized_plan_result)
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

            if first_pending_index >= len(merged_steps):
                runtime_state["status"] = "finished"
                runtime_state["finished_tick"] = old_runtime.get("last_run_tick")

            if preserve_history:
                runtime_state["step_history"] = copy.deepcopy(old_history)
            else:
                runtime_state["step_history"] = []

            runtime_state["step_history"].append(
                {
                    "event": "replan",
                    "reason": reason or "",
                    "failed_step": failed_step,
                    "preserved_completed_steps": len(preserved_results),
                    "at": self._now_iso(),
                }
            )

            runtime_state["execution_log"] = copy.deepcopy(old_execution_log)
            runtime_state["execution_log"].append(
                {
                    "type": "replan",
                    "reason": reason or "",
                    "failed_step": failed_step,
                    "replan_count": runtime_state["replan_count"],
                    "steps_total": len(merged_steps),
                    "preserved_completed_steps": len(preserved_results),
                    "first_pending_index": first_pending_index,
                    "at": self._now_iso(),
                }
            )

            self._save_json(runtime_file, runtime_state)
            self._save_json(runtime_state["execution_log_file"], runtime_state["execution_log"])

            self._append_replan_log(
                task_dir=task_dir,
                reason=reason,
                failed_step=failed_step,
                new_step_count=len(merged_steps),
                replan_count=runtime_state["replan_count"],
                preserved_completed_steps=len(preserved_results),
                first_pending_index=first_pending_index,
            )

            return {
                "ok": True,
                "replanned": True,
                "reason": reason,
                "step_count": len(merged_steps),
                "plan_file": plan_file,
                "runtime_file": runtime_file,
                "preserved_completed_steps": len(preserved_results),
                "first_pending_index": first_pending_index,
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
    # Completed step resume / merge
    # =========================================================

    def _build_completed_step_registry(
        self,
        old_steps: List[Dict[str, Any]],
        old_results: List[Dict[str, Any]],
        old_step_results: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        registry: Dict[str, Dict[str, Any]] = {}

        combined_results: List[Dict[str, Any]] = []
        for item in old_results:
            if isinstance(item, dict):
                combined_results.append(item)
        for item in old_step_results:
            if isinstance(item, dict):
                combined_results.append(item)

        for result in combined_results:
            if not self._result_is_success(result):
                continue

            step_obj = result.get("step", {})
            if not isinstance(step_obj, dict):
                step_obj = {}

            normalized_step = self._normalize_single_step(
                step=step_obj,
                task_name=str(step_obj.get("task_name", "") or ""),
                step_index=int(step_obj.get("step_index", 0) or 0),
                step_count=int(step_obj.get("step_count", 0) or 0),
            )

            key = self._match_key_for_step(normalized_step)
            if not key:
                continue

            registry[key] = {
                "step": copy.deepcopy(normalized_step),
                "result": copy.deepcopy(result),
            }

        # 補一層：如果 old_steps 本身已有 status=completed 也納入
        for step in old_steps:
            if not isinstance(step, dict):
                continue
            status = str(step.get("status", "") or "").strip().lower()
            if status != "completed":
                continue

            normalized_step = self._normalize_single_step(
                step=step,
                task_name="",
                step_index=int(step.get("step_index", 0) or 0),
                step_count=int(step.get("step_count", 0) or 0),
            )
            key = self._match_key_for_step(normalized_step)
            if not key or key in registry:
                continue

            registry[key] = {
                "step": copy.deepcopy(normalized_step),
                "result": {
                    "ok": True,
                    "error": None,
                    "result": {},
                    "step": copy.deepcopy(normalized_step),
                    "step_key": normalized_step.get("step_key"),
                    "idempotent": normalized_step.get("idempotent"),
                    "side_effects": normalized_step.get("side_effects"),
                    "retry_safe": normalized_step.get("retry_safe"),
                    "replan_safe": normalized_step.get("replan_safe"),
                    "safety_class": normalized_step.get("safety_class"),
                },
            }

        return registry

    def _merge_completed_steps_into_new_plan(
        self,
        new_steps: List[Dict[str, Any]],
        completed_registry: Dict[str, Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int]:
        merged_steps: List[Dict[str, Any]] = []
        preserved_results: List[Dict[str, Any]] = []

        for step in new_steps:
            normalized = copy.deepcopy(step)
            match_key = self._match_key_for_step(normalized)

            matched = completed_registry.get(match_key) if match_key else None
            if matched and self._can_preserve_completed_step(normalized):
                normalized["status"] = "completed"
                normalized["resumed_from_previous_run"] = True

                old_result = copy.deepcopy(matched.get("result", {}))
                old_result["step"] = copy.deepcopy(normalized)
                old_result["step_key"] = normalized.get("step_key")
                old_result["idempotent"] = normalized.get("idempotent")
                old_result["side_effects"] = normalized.get("side_effects")
                old_result["retry_safe"] = normalized.get("retry_safe")
                old_result["replan_safe"] = normalized.get("replan_safe")
                old_result["safety_class"] = normalized.get("safety_class")

                preserved_results.append(old_result)
            else:
                normalized["status"] = "pending"

            merged_steps.append(normalized)

        first_pending_index = len(merged_steps)
        for idx, step in enumerate(merged_steps):
            status = str(step.get("status", "") or "").strip().lower()
            if status != "completed":
                first_pending_index = idx
                break

        return merged_steps, preserved_results, first_pending_index

    def _can_preserve_completed_step(self, step: Dict[str, Any]) -> bool:
        """
        目前策略：
        - read-only steps 可以保留
        - write_file 可以保留（因為檔案已產生，避免重跑）
        - command / delete / POST API 先不要自動保留
        """
        step_type = str(step.get("type", "") or "").strip().lower()

        if step_type in self.READ_ONLY_STEP_TYPES:
            return True

        if step_type == "write_file":
            return True

        explicit = step.get("replan_safe")
        if isinstance(explicit, bool):
            return explicit

        return False

    def _result_is_success(self, result: Dict[str, Any]) -> bool:
        if not isinstance(result, dict):
            return False

        ok = result.get("ok")
        if isinstance(ok, bool):
            return ok

        status = str(result.get("status", "") or "").strip().lower()
        return status in {"ok", "success", "completed", "done"}

    def _match_key_for_step(self, step: Dict[str, Any]) -> str:
        step_key = str(step.get("step_key", "") or "").strip()
        if step_key:
            return f"step_key:{step_key}"

        signature = self._build_step_signature(step)
        if signature:
            return f"signature:{signature}"

        return ""

    def _build_step_signature(self, step: Dict[str, Any]) -> str:
        safe_step = copy.deepcopy(step or {})
        payload = {
            "type": safe_step.get("type"),
            "command": safe_step.get("command"),
            "path": safe_step.get("path"),
            "url": safe_step.get("url"),
            "method": safe_step.get("method"),
            "content": safe_step.get("content"),
            "query": safe_step.get("query"),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    # =========================================================
    # Step normalization / metadata
    # =========================================================

    def _normalize_steps(self, steps: List[Dict[str, Any]], task_name: str) -> List[Dict[str, Any]]:
        normalized_steps: List[Dict[str, Any]] = []
        total = len(steps)

        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            normalized_steps.append(
                self._normalize_single_step(
                    step=step,
                    task_name=task_name,
                    step_index=index,
                    step_count=total,
                )
            )

        return normalized_steps

    def _normalize_single_step(
        self,
        step: Dict[str, Any],
        task_name: str,
        step_index: int,
        step_count: int,
    ) -> Dict[str, Any]:
        normalized = copy.deepcopy(step or {})
        step_type = str(normalized.get("type", "") or "").strip().lower()

        if not step_type:
            step_type = "unknown"
            normalized["type"] = step_type

        normalized["step_index"] = int(normalized.get("step_index", step_index) or step_index)
        normalized["step_count"] = int(normalized.get("step_count", step_count) or step_count)

        if not isinstance(normalized.get("produces_files"), list):
            normalized["produces_files"] = self._infer_produces_files(normalized)

        if not isinstance(normalized.get("consumes_files"), list):
            normalized["consumes_files"] = self._infer_consumes_files(normalized)

        if not isinstance(normalized.get("external_effects"), list):
            normalized["external_effects"] = self._infer_external_effects(normalized)

        normalized["produces_files"] = self._normalize_string_list(normalized.get("produces_files"))
        normalized["consumes_files"] = self._normalize_string_list(normalized.get("consumes_files"))
        normalized["external_effects"] = self._normalize_string_list(normalized.get("external_effects"))

        metadata_defaults = self._infer_step_metadata_defaults(normalized)
        for key, value in metadata_defaults.items():
            if key not in normalized:
                normalized[key] = value

        step_key = normalized.get("step_key")
        if not isinstance(step_key, str) or not step_key.strip():
            normalized["step_key"] = self._build_step_key(
                task_name=task_name,
                step_index=normalized["step_index"],
                step=normalized,
            )

        return normalized

    def _infer_step_metadata_defaults(self, step: Dict[str, Any]) -> Dict[str, Any]:
        step_type = str(step.get("type", "") or "").strip().lower()
        metadata: Dict[str, Any] = {}

        if step_type in self.READ_ONLY_STEP_TYPES:
            metadata["idempotent"] = True
            metadata["side_effects"] = False
            metadata["retry_safe"] = True
            metadata["replan_safe"] = True
            metadata["safety_class"] = "read_only"
            return metadata

        if step_type == "write_file":
            metadata["idempotent"] = False
            metadata["side_effects"] = True
            metadata["retry_safe"] = False
            metadata["replan_safe"] = False
            metadata["safety_class"] = "file_write"
            return metadata

        if step_type == "delete_file":
            metadata["idempotent"] = False
            metadata["side_effects"] = True
            metadata["retry_safe"] = False
            metadata["replan_safe"] = False
            metadata["safety_class"] = "file_delete"
            return metadata

        if step_type in {"command", "shell", "execute"}:
            metadata["idempotent"] = False
            metadata["side_effects"] = True
            metadata["retry_safe"] = False
            metadata["replan_safe"] = False
            metadata["safety_class"] = "command"
            return metadata

        if step_type in {"call_api", "http_request"}:
            method = str(step.get("method", "") or "POST").strip().upper()
            if method == "GET":
                metadata["idempotent"] = True
                metadata["side_effects"] = False
                metadata["retry_safe"] = True
                metadata["replan_safe"] = True
                metadata["safety_class"] = "http_read"
            else:
                metadata["idempotent"] = False
                metadata["side_effects"] = True
                metadata["retry_safe"] = False
                metadata["replan_safe"] = False
                metadata["safety_class"] = "http_write"
            return metadata

        metadata["idempotent"] = False
        metadata["side_effects"] = False
        metadata["retry_safe"] = False
        metadata["replan_safe"] = False
        metadata["safety_class"] = "unknown"
        return metadata

    def _infer_produces_files(self, step: Dict[str, Any]) -> List[str]:
        step_type = str(step.get("type", "") or "").strip().lower()
        path = str(step.get("path", "") or "").strip()

        if step_type == "write_file" and path:
            return [path]

        return []

    def _infer_consumes_files(self, step: Dict[str, Any]) -> List[str]:
        step_type = str(step.get("type", "") or "").strip().lower()
        path = str(step.get("path", "") or "").strip()

        if step_type == "read_file" and path:
            return [path]

        return []

    def _infer_external_effects(self, step: Dict[str, Any]) -> List[str]:
        step_type = str(step.get("type", "") or "").strip().lower()

        if step_type in {"command", "shell", "execute"}:
            command = str(step.get("command", "") or "").strip()
            return [f"command:{command}"] if command else []

        if step_type in {"call_api", "http_request"}:
            method = str(step.get("method", "") or "POST").strip().upper()
            url = str(step.get("url", "") or "").strip()
            return [f"http:{method}:{url}"] if url else []

        if step_type == "delete_file":
            path = str(step.get("path", "") or "").strip()
            return [f"delete:{path}"] if path else []

        return []

    def _build_step_key(
        self,
        task_name: str,
        step_index: int,
        step: Dict[str, Any],
    ) -> str:
        safe_step = copy.deepcopy(step or {})
        safe_step.pop("step_key", None)

        raw = {
            "task_name": task_name,
            "step_index": step_index,
            "type": safe_step.get("type"),
            "command": safe_step.get("command"),
            "path": safe_step.get("path"),
            "url": safe_step.get("url"),
            "method": safe_step.get("method"),
            "content": safe_step.get("content"),
            "query": safe_step.get("query"),
        }

        payload = json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
        return f"step_{step_index}_{digest}"

    def _normalize_string_list(self, value: Any) -> List[str]:
        if value is None:
            return []

        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []

        if isinstance(value, list):
            result: List[str] = []
            for item in value:
                if item is None:
                    continue
                text = str(item).strip()
                if text:
                    result.append(text)
            return result

        text = str(value).strip()
        return [text] if text else []

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

        build_plan = getattr(self.planner, "build_plan", None)
        if callable(build_plan):
            result = build_plan(goal=goal, task_dir=task_dir)
            return self._normalize_planner_output(goal=goal, result=result, planner_mode="planner.build_plan")

        plan_fn = getattr(self.planner, "plan", None)
        if callable(plan_fn):
            try:
                result = plan_fn(
                    context={"workspace": task_dir, "task_dir": task_dir},
                    user_input=goal,
                    route=None,
                )
            except TypeError:
                try:
                    result = plan_fn(goal=goal, task_dir=task_dir)
                except TypeError:
                    result = plan_fn(goal)
            return self._normalize_planner_output(goal=goal, result=result, planner_mode="planner.plan")

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
        preserved_completed_steps: int = 0,
        first_pending_index: int = 0,
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
                "preserved_completed_steps": preserved_completed_steps,
                "first_pending_index": first_pending_index,
            }
        )

        self._save_json(log_file, existing)

    def _read_json(self, file_path: str, default: Any) -> Any:
        if not os.path.exists(file_path):
            return copy.deepcopy(default)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return copy.deepcopy(default)

    def _save_json(self, file_path: str, data: Any) -> None:
        parent = os.path.dirname(file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _now_iso(self) -> str:
        return datetime.now().isoformat(timespec="seconds")