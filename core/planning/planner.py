from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional

from core.runtime.trace_logger import ensure_trace_logger


class Planner:
    """
    Deterministic Planner v12 + TRACE
    """

    def __init__(
        self,
        memory_store: Any = None,
        runtime_store: Any = None,
        step_executor: Any = None,
        tool_registry: Any = None,
        workspace_dir: str = "workspace",
        workspace_root: Optional[str] = None,
        debug: bool = False,
        trace_logger: Optional[Any] = None,
    ) -> None:
        self.memory_store = memory_store
        self.runtime_store = runtime_store
        self.step_executor = step_executor
        self.tool_registry = tool_registry
        self.workspace_dir = workspace_root or workspace_dir or "workspace"
        self.debug = debug
        self.trace_logger = ensure_trace_logger(trace_logger)

        print("### USING NEW PLANNER (TRACE ENABLED) ###")

    # ============================================================
    # public api
    # ============================================================

    def plan(
        self,
        context: Optional[Dict[str, Any]] = None,
        user_input: str = "",
        route: Any = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        context = context or {}
        text = str(user_input or context.get("user_input") or "").strip()

        self.trace_logger.log_decision(
            title="planner input",
            message=text,
            source="planner",
            raw={
                "context": context,
                "route": route,
            },
        )

        if not text:
            return {
                "planner_mode": "deterministic_v12",
                "intent": "respond",
                "final_answer": "空白輸入",
                "steps": [],
            }

        raw_steps = self._plan_steps(text=text, route=route)

        task_name = self._infer_task_name(
            task_dir=str(context.get("workspace", "") or ""),
            goal=text
        )

        steps = self._apply_step_metadata(raw_steps, task_name=task_name)

        intent = self._infer_intent(text=text, route=route, steps=steps)

        self.trace_logger.log_decision(
            title="planner result",
            message=f"steps={len(steps)}, intent={intent}",
            source="planner",
            raw={
                "steps": steps,
                "intent": intent,
                "task_name": task_name,
            },
        )

        return {
            "planner_mode": "deterministic_v12",
            "intent": intent,
            "final_answer": f"已規劃 {len(steps)} 個步驟",
            "steps": steps,
        }

    def run(self, *args, **kwargs):
        return self.plan(*args, **kwargs)

    # ============================================================
    # core planning
    # ============================================================

    def _plan_steps(self, text: str, route: Any = None) -> List[Dict[str, Any]]:
        clauses = self._split_clauses(text)

        self.trace_logger.log_decision(
            title="split clauses",
            message=f"{len(clauses)} clauses",
            source="planner",
            raw={"clauses": clauses},
        )

        steps: List[Dict[str, Any]] = []

        for clause in clauses:
            sub_steps = self._plan_single_clause(clause, route=route)
            steps.extend(sub_steps)

        return steps

    def _plan_single_clause(self, text: str, route: Any = None) -> List[Dict[str, Any]]:
        stripped = str(text or "").strip()

        self.trace_logger.log_decision(
            title="analyze clause",
            message=stripped,
            source="planner",
        )

        if not stripped:
            return []

        if self._extract_command(stripped):
            cmd = self._extract_command(stripped)

            self.trace_logger.log_decision(
                title="command detected",
                message=cmd,
                source="planner",
            )

            return [{"type": "command", "command": cmd}]

        read_path = self._extract_file_path(stripped)
        if read_path and self._looks_like_read(stripped):

            self.trace_logger.log_decision(
                title="read detected",
                message=read_path,
                source="planner",
            )

            return [{"type": "read_file", "path": read_path}]

        write = self._extract_write_request(stripped)
        if write:

            self.trace_logger.log_decision(
                title="write detected",
                message=write["path"],
                source="planner",
                raw=write,
            )

            return [{"type": "write_file", **write}]

        if self._looks_like_search(stripped):

            self.trace_logger.log_decision(
                title="search detected",
                message=stripped,
                source="planner",
            )

            return [{"type": "web_search", "query": stripped}]

        return []

    # ============================================================
    # utils（保留你原本邏輯）
    # ============================================================

    def _split_clauses(self, text: str) -> List[str]:
        parts = re.split(r"[，,。；;]|然後|接著|之後|and then", text)
        return [p.strip() for p in parts if p.strip()]

    def _extract_command(self, text: str) -> Optional[str]:
        if text.lower().startswith(("python ", "cmd ", "powershell ")):
            return text
        return None

    def _extract_file_path(self, text: str) -> Optional[str]:
        m = re.search(r'([A-Za-z0-9_\-./\\]+?\.(?:py|txt|md|json))', text)
        return m.group(1) if m else None

    def _looks_like_read(self, text: str) -> bool:
        return any(k in text for k in ["讀取", "查看", "read", "open"])

    def _extract_write_request(self, text: str) -> Optional[Dict[str, str]]:
        if "寫" in text or "create" in text:
            path = self._extract_file_path(text)
            if path:
                return {"path": path, "content": ""}
        return None

    def _looks_like_search(self, text: str) -> bool:
        return any(k in text for k in ["搜尋", "search", "查"])

    def _infer_task_name(self, task_dir: str, goal: str) -> str:
        return "task_" + hashlib.sha1(goal.encode()).hexdigest()[:6]

    def _apply_step_metadata(self, steps: List[Dict[str, Any]], task_name: str) -> List[Dict[str, Any]]:
        return steps

    def _infer_intent(self, text: str, route: Any, steps: List[Dict[str, Any]]) -> str:
        if steps:
            return steps[0].get("type", "unknown")
        return "respond"