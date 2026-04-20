from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple

from core.planning.planner_document_logic import (
    plan_document_flow,
    plan_structured_document_task,
)
from core.planning.planner_rule_parser import (
    extract_command,
    extract_file_path,
    extract_run_python_request,
    extract_verify_request,
    extract_write_request,
    has_verify_intent,
    infer_path_scope,
    looks_like_read,
    looks_like_search,
    resolve_read_path,
)
from core.runtime.trace_logger import ensure_trace_logger


class Planner:
    """
    Deterministic Planner v28

    本版重點：
    1. 保留 document flow 偵測
    2. 保留 command / write / ensure / read / search 規則
    3. 保留 run_python 規則
    4. 保留 verify 規則
    5. verify 類句型先於 document flow 判定
    6. 修正 action_items / summary task 句型優先序
    7. 保留使用者指定的 source / output path
    8. 新增「結構化 document task 入口」
    9. 新增 requirement-pack 多交付物規劃入口
    """

    _banner_printed = False

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

        if not Planner._banner_printed:
            print("### USING PLANNER v28 (DOCUMENT + REQUIREMENT PACK ENTRY) ###")
            Planner._banner_printed = True

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
                "kwargs": kwargs,
            },
        )

        try:
            structured_document_steps = self._plan_structured_document_task(
                context=context,
                route=route,
                kwargs=kwargs,
            )

            if structured_document_steps is not None:
                task_name = self._infer_task_name(
                    task_dir=str(context.get("workspace", "") or ""),
                    goal=text or "structured_document_task",
                )

                steps = self._apply_step_metadata(structured_document_steps, task_name=task_name)
                intent = self._infer_intent(text=text, route=route, steps=steps)

                result = self._build_plan_result(
                    steps=steps,
                    intent=intent,
                    final_answer=f"已規劃 {len(steps)} 個步驟",
                    fallback_used=False,
                    error=None,
                )

                self.trace_logger.log_decision(
                    title="planner structured document result",
                    message=f"steps={len(steps)}, intent={intent}",
                    source="planner",
                    raw={
                        "steps": steps,
                        "intent": intent,
                        "task_name": task_name,
                        "result": result,
                    },
                )
                return result

            if not text:
                result = self._build_plan_result(
                    steps=[],
                    intent="respond",
                    final_answer="空白輸入",
                    fallback_used=False,
                    error=None,
                )
                self.trace_logger.log_decision(
                    title="planner result",
                    message="empty input",
                    source="planner",
                    raw=result,
                )
                return result

            raw_steps, fallback_used = self._plan_steps(text=text, route=route)

            task_name = self._infer_task_name(
                task_dir=str(context.get("workspace", "") or ""),
                goal=text,
            )

            steps = self._apply_step_metadata(raw_steps, task_name=task_name)
            intent = self._infer_intent(text=text, route=route, steps=steps)

            result = self._build_plan_result(
                steps=steps,
                intent=intent,
                final_answer=f"已規劃 {len(steps)} 個步驟",
                fallback_used=fallback_used,
                error=None,
            )

            self.trace_logger.log_decision(
                title="planner result",
                message=f"steps={len(steps)}, intent={intent}, fallback={fallback_used}",
                source="planner",
                raw={
                    "steps": steps,
                    "intent": intent,
                    "task_name": task_name,
                    "result": result,
                },
            )
            return result

        except Exception as e:
            error_message = f"planner failed: {e}"
            result = self._build_plan_result(
                steps=[],
                intent="respond",
                final_answer=error_message,
                fallback_used=False,
                error=error_message,
            )

            self.trace_logger.log_decision(
                title="planner exception",
                message=error_message,
                source="planner",
                raw=result,
            )
            return result

    def run(self, *args, **kwargs):
        return self.plan(*args, **kwargs)

    # ============================================================
    # structured document task
    # ============================================================

    def _plan_structured_document_task(
        self,
        context: Optional[Dict[str, Any]] = None,
        route: Any = None,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        return plan_structured_document_task(
            context=context,
            route=route,
            kwargs=kwargs,
            trace_logger=self.trace_logger,
        )

    # ============================================================
    # core planning
    # ============================================================

    def _plan_steps(self, text: str, route: Any = None) -> Tuple[List[Dict[str, Any]], bool]:
        stripped = str(text or "").strip()

        looks_multi_clause = len(self._split_clauses(stripped)) > 1
        early_verify = None
        if not looks_multi_clause and self._has_verify_intent(stripped):
            early_verify = self._extract_verify_request(stripped, last_path=None)
        if early_verify:
            verify_path = str(early_verify.get("path") or "").strip()
            self.trace_logger.log_decision(
                title="early verify detected",
                message=verify_path or stripped,
                source="planner",
                raw={"step": early_verify},
            )
            return [early_verify], False

        special_document_steps = self._plan_document_flow(stripped)
        if special_document_steps is not None:
            return special_document_steps, False

        clauses = self._split_clauses(text)

        self.trace_logger.log_decision(
            title="split clauses",
            message=f"{len(clauses)} clauses",
            source="planner",
            raw={"clauses": clauses},
        )

        steps: List[Dict[str, Any]] = []
        fallback_used = False
        last_path: Optional[str] = None

        for clause in clauses:
            sub_steps, clause_fallback_used, last_path = self._plan_single_clause(
                text=clause,
                route=route,
                last_path=last_path,
            )
            if clause_fallback_used:
                fallback_used = True
            steps.extend(sub_steps)

        return steps, fallback_used

    # ============================================================
    # document flow
    # ============================================================

    def _plan_document_flow(self, text: str) -> Optional[List[Dict[str, Any]]]:
        return plan_document_flow(
            text=text,
            trace_logger=self.trace_logger,
        )

    # ============================================================
    # per-clause planning
    # ============================================================

    def _plan_single_clause(
        self,
        text: str,
        route: Any = None,
        last_path: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], bool, Optional[str]]:
        stripped = str(text or "").strip()

        self.trace_logger.log_decision(
            title="analyze clause",
            message=stripped,
            source="planner",
            raw={"last_path": last_path},
        )

        if not stripped:
            return [], False, last_path

        cmd = self._extract_command(stripped)
        if cmd:
            self.trace_logger.log_decision(
                title="command detected",
                message=cmd,
                source="planner",
            )
            return [{"type": "command", "command": cmd}], False, last_path

        run_python = self._extract_run_python_request(stripped)
        if run_python:
            self.trace_logger.log_decision(
                title="run_python detected",
                message=run_python["path"],
                source="planner",
                raw=run_python,
            )
            return [run_python], False, run_python["path"]

        verify = self._extract_verify_request(stripped, last_path=last_path)
        if verify:
            verify_path = str(verify.get("path") or "").strip() or last_path
            self.trace_logger.log_decision(
                title="verify detected",
                message=verify_path,
                source="planner",
                raw=verify,
            )
            return [verify], False, verify_path or last_path

        write = self._extract_write_request(stripped)
        if write:
            current_path = str(write.get("path") or "").strip() or last_path
            content = write.get("content", "")
            has_explicit_content = bool(write.get("has_explicit_content", False))

            if has_explicit_content:
                normalized_step = {
                    "type": "write_file",
                    "path": current_path or "",
                    "scope": self._infer_path_scope(current_path or ""),
                    "content": content,
                }
                step_type = "write detected"
            else:
                normalized_step = {
                    "type": "ensure_file",
                    "path": current_path or "",
                    "scope": self._infer_path_scope(current_path or ""),
                }
                step_type = "ensure_file detected"

            self.trace_logger.log_decision(
                title=step_type,
                message=normalized_step.get("path", ""),
                source="planner",
                raw=normalized_step,
            )
            return [normalized_step], False, current_path

        if self._looks_like_read(stripped):
            read_path = self._resolve_read_path(stripped, last_path=last_path)
            if read_path:
                self.trace_logger.log_decision(
                    title="read detected",
                    message=read_path,
                    source="planner",
                    raw={
                        "text": stripped,
                        "resolved_from_last_path": self._extract_file_path(stripped) is None and last_path is not None,
                    },
                )
                return [{"type": "read_file", "path": read_path}], False, read_path

        if self._looks_like_search(stripped):
            self.trace_logger.log_decision(
                title="search detected",
                message=stripped,
                source="planner",
            )
            return [{"type": "web_search", "query": stripped}], False, last_path

        self.trace_logger.log_decision(
            title="fallback detected",
            message=stripped,
            source="planner",
            raw={
                "reason": "no deterministic rule matched",
                "last_path": last_path,
            },
        )
        return [{"type": "llm", "prompt": stripped}], True, last_path

    # ============================================================
    # result builder
    # ============================================================

    def _build_plan_result(
        self,
        steps: List[Dict[str, Any]],
        intent: str,
        final_answer: str,
        fallback_used: bool,
        error: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "ok": error is None,
            "planner_mode": "deterministic_v27",
            "intent": intent,
            "final_answer": final_answer,
            "steps": steps,
            "error": error,
            "meta": {
                "fallback_used": fallback_used,
                "step_count": len(steps),
            },
        }

    # ============================================================
    # clause splitting
    # ============================================================

    def _split_clauses(self, text: str) -> List[str]:
        normalized = str(text or "").strip()

        parts = re.split(
            r"(?:，|,|。|；|;|\n+|\r\n+|然後|接著|之後|再來|再|and then|then)",
            normalized,
            flags=re.IGNORECASE,
        )

        cleaned = [p.strip() for p in parts if p and p.strip()]
        return cleaned

    # ============================================================
    # deterministic rule parser adapter
    # ============================================================

    def _extract_command(self, text: str) -> Optional[str]:
        return extract_command(text)

    def _extract_run_python_request(self, text: str) -> Optional[Dict[str, Any]]:
        return extract_run_python_request(text)

    def _infer_path_scope(self, path: str) -> str:
        return infer_path_scope(path)

    def _has_verify_intent(self, text: str) -> bool:
        return has_verify_intent(text)

    def _extract_verify_request(self, text: str, last_path: Optional[str]) -> Optional[Dict[str, Any]]:
        return extract_verify_request(text, last_path)

    def _extract_file_path(self, text: str) -> Optional[str]:
        return extract_file_path(text)

    def _looks_like_read(self, text: str) -> bool:
        return looks_like_read(text)

    def _resolve_read_path(self, text: str, last_path: Optional[str]) -> Optional[str]:
        return resolve_read_path(text, last_path)

    def _extract_write_request(self, text: str) -> Optional[Dict[str, Any]]:
        return extract_write_request(text)

    def _looks_like_search(self, text: str) -> bool:
        return looks_like_search(text)

    # ============================================================
    # metadata
    # ============================================================

    def _infer_task_name(self, task_dir: str, goal: str) -> str:
        return "task_" + hashlib.sha1(goal.encode("utf-8")).hexdigest()[:6]

    def _apply_step_metadata(self, steps: List[Dict[str, Any]], task_name: str) -> List[Dict[str, Any]]:
        enriched: List[Dict[str, Any]] = []

        for idx, step in enumerate(steps, start=1):
            item = dict(step)
            item.setdefault("id", f"{task_name}_step_{idx}")
            item.setdefault("task_name", task_name)
            enriched.append(item)

        return enriched

    def _infer_intent(self, text: str, route: Any, steps: List[Dict[str, Any]]) -> str:
        if not steps:
            return "respond"

        first_type = str(steps[0].get("type") or "").strip().lower()
        if len(steps) >= 3:
            second_type = str(steps[1].get("type") or "").strip().lower()
            third_type = str(steps[2].get("type") or "").strip().lower()
            if first_type == "read_file" and second_type == "llm" and third_type == "write_file":
                llm_mode = str(steps[1].get("mode") or "").strip().lower()
                if llm_mode == "action_items":
                    return "action_items"
                if llm_mode == "summary":
                    return "summary"

        return first_type or "unknown"