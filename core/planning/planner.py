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
    Deterministic Planner v30

    本版重點：
    1. 保留 document flow 偵測
    2. 保留 command / write / ensure / read / search 規則
    3. 保留 run_python 規則
    4. 保留 verify 規則
    5. verify 類句型先於 document flow 判定
    6. 保留結構化 document task 入口
    7. planner result contract 固定化
    8. step schema 正規化
    9. 保留 v29 action layer
    10. 新增 multi-step deterministic planner：
        - read_file -> llm(summary/action_items) -> write_file
    """

    _banner_printed = False
    PLANNER_MODE = "deterministic_v30"

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
            print("### USING PLANNER v30 (MULTI-STEP + ACTION LAYER + DOCUMENT ENTRY) ###")
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

                steps = self._apply_step_metadata(
                    structured_document_steps,
                    task_name=task_name,
                )
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

        multi_steps = self._plan_multi_step_task(stripped)
        if multi_steps is not None:
            self.trace_logger.log_decision(
                title="multi-step detected",
                message=stripped,
                source="planner",
                raw={"steps": multi_steps},
            )
            return multi_steps, False

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
    # multi-step task planning
    # ============================================================

    def _plan_multi_step_task(self, text: str) -> Optional[List[Dict[str, Any]]]:
        parsed = self._match_read_transform_write(text)
        if parsed is None:
            return None

        source_path = parsed["source_path"]
        output_path = parsed["output_path"]
        llm_mode = parsed["llm_mode"]

        return [
            {
                "type": "read_file",
                "path": source_path,
            },
            {
                "type": "llm",
                "mode": llm_mode,
                "prompt": self._build_transform_prompt(llm_mode=llm_mode, source_path=source_path),
            },
            {
                "type": "write_file",
                "path": output_path,
                "scope": self._infer_path_scope(output_path),
                "content": "{{previous_result}}",
            },
        ]

    def _match_read_transform_write(self, text: str) -> Optional[Dict[str, str]]:
        stripped = str(text or "").strip()
        lowered = stripped.lower()

        llm_mode = self._detect_transform_mode(lowered)
        if llm_mode is None:
            return None

        output_path = self._detect_output_path_from_text(stripped, llm_mode=llm_mode)
        if not output_path:
            return None

        source_path = self._detect_source_path_from_text(stripped, output_path=output_path)
        if not source_path:
            return None

        return {
            "source_path": source_path,
            "output_path": output_path,
            "llm_mode": llm_mode,
        }

    def _detect_transform_mode(self, lowered: str) -> Optional[str]:
        if any(token in lowered for token in ["action items", "action-items", "todo list", "extract actions"]):
            return "action_items"
        if any(token in lowered for token in ["summarize", "summary", "make summary", "create summary"]):
            return "summary"
        return None

    def _detect_output_path_from_text(self, text: str, llm_mode: str) -> Optional[str]:
        stripped = str(text or "").strip()

        patterns = [
            r"\bto\s+([^\s,;]+)",
            r"\binto\s+([^\s,;]+)",
            r"\bas\s+([^\s,;]+)",
            r"\bwrite\s+(?:to\s+)?([^\s,;]+)$",
        ]

        for pattern in patterns:
            match = re.search(pattern, stripped, flags=re.IGNORECASE)
            if not match:
                continue
            candidate = self._normalize_requested_path(match.group(1))
            if self._looks_like_file_candidate(candidate):
                return candidate

        # default output names
        if llm_mode == "summary":
            return "workspace/shared/summary.txt"
        if llm_mode == "action_items":
            return "workspace/shared/action_items.txt"
        return None

    def _detect_source_path_from_text(self, text: str, output_path: str) -> Optional[str]:
        raw_candidates = re.findall(
            r"(?:[A-Za-z]:[\\/][^\s,;]+|(?:workspace|shared|sandbox)[\\/][^\s,;]+|[^\s,;]+\.(?:txt|md|json|log|csv))",
            text,
            flags=re.IGNORECASE,
        )

        normalized_candidates: List[str] = []
        for candidate in raw_candidates:
            normalized = self._normalize_requested_path(candidate)
            if normalized and normalized not in normalized_candidates:
                normalized_candidates.append(normalized)

        for candidate in normalized_candidates:
            if candidate != output_path:
                return candidate

        read_match = re.search(r"\bread\s+([^\s,;]+)", text, flags=re.IGNORECASE)
        if read_match:
            candidate = self._normalize_requested_path(read_match.group(1))
            if candidate and candidate != output_path:
                return candidate

        summarize_match = re.search(
            r"\b(?:summarize|summary|action items from|extract actions from)\s+([^\s,;]+)",
            text,
            flags=re.IGNORECASE,
        )
        if summarize_match:
            candidate = self._normalize_requested_path(summarize_match.group(1))
            if candidate and candidate != output_path:
                return candidate

        return None

    def _build_transform_prompt(self, llm_mode: str, source_path: str) -> str:
        if llm_mode == "summary":
            return f"Summarize the content from {source_path} into concise plain text."
        if llm_mode == "action_items":
            return f"Extract action items from the content of {source_path} as concise plain text."
        return f"Process the content from {source_path}."

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
        lowered = stripped.lower()

        self.trace_logger.log_decision(
            title="analyze clause",
            message=stripped,
            source="planner",
            raw={"last_path": last_path},
        )

        if not stripped:
            return [], False, last_path

        # ========================================================
        # v29/v30 ACTION LAYER
        # ========================================================

        action_steps, action_last_path = self._plan_action_clause(
            text=stripped,
            lowered=lowered,
            last_path=last_path,
        )
        if action_steps is not None:
            self.trace_logger.log_decision(
                title="action layer detected",
                message=stripped,
                source="planner",
                raw={
                    "steps": action_steps,
                    "last_path": action_last_path,
                },
            )
            return action_steps, False, action_last_path

        # ========================================================
        # existing deterministic rules
        # ========================================================

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
                message=str(run_python.get("path") or ""),
                source="planner",
                raw=run_python,
            )
            run_path = str(run_python.get("path") or "").strip() or last_path
            if run_path:
                run_python["path"] = run_path
            return [run_python], False, run_python.get("path") or last_path

        verify = self._extract_verify_request(stripped, last_path=last_path)
        if verify:
            verify_path = str(verify.get("path") or "").strip() or last_path
            self.trace_logger.log_decision(
                title="verify detected",
                message=verify_path or "",
                source="planner",
                raw=verify,
            )
            if verify_path:
                verify["path"] = verify_path
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
    # action layer
    # ============================================================

    def _plan_action_clause(
        self,
        text: str,
        lowered: str,
        last_path: Optional[str] = None,
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        explicit_write = self._match_write_file_request(text)
        if explicit_write is not None:
            path = explicit_write["path"]
            content = explicit_write["content"]

            return [
                {
                    "type": "ensure_file",
                    "path": path,
                    "scope": self._infer_path_scope(path),
                },
                {
                    "type": "write_file",
                    "path": path,
                    "scope": self._infer_path_scope(path),
                    "content": content,
                },
            ], path

        command_request = self._match_command_request(text)
        if command_request is not None:
            return [
                {
                    "type": "command",
                    "command": command_request,
                }
            ], last_path

        python_request = self._match_run_python_request(text)
        if python_request is not None:
            return [
                {
                    "type": "run_python",
                    "path": python_request,
                }
            ], python_request

        hello_shortcut = self._match_hello_file_shortcut(lowered)
        if hello_shortcut is not None:
            path, content = hello_shortcut
            return [
                {
                    "type": "ensure_file",
                    "path": path,
                    "scope": self._infer_path_scope(path),
                },
                {
                    "type": "write_file",
                    "path": path,
                    "scope": self._infer_path_scope(path),
                    "content": content,
                },
            ], path

        create_empty = self._match_create_empty_file_request(text)
        if create_empty is not None:
            return [
                {
                    "type": "ensure_file",
                    "path": create_empty,
                    "scope": self._infer_path_scope(create_empty),
                }
            ], create_empty

        append_write = self._match_write_into_existing_request(text, last_path=last_path)
        if append_write is not None:
            path = append_write["path"]
            content = append_write["content"]
            return [
                {
                    "type": "write_file",
                    "path": path,
                    "scope": self._infer_path_scope(path),
                    "content": content,
                }
            ], path

        return None, last_path

    def _match_hello_file_shortcut(self, lowered: str) -> Optional[Tuple[str, str]]:
        candidates = {
            "write hello file",
            "create hello file",
            "make hello file",
            "write a hello file",
            "create a hello file",
            "make a hello file",
        }
        if lowered in candidates:
            return "workspace/shared/hello.txt", "hello"
        return None

    def _match_command_request(self, text: str) -> Optional[str]:
        stripped = str(text or "").strip()

        patterns = [
            r"^(?:run|execute|do)\s+command\s*:\s*(.+)$",
            r"^(?:run|execute)\s+this\s+command\s*:\s*(.+)$",
            r"^(?:cmd|command)\s*:\s*(.+)$",
        ]

        for pattern in patterns:
            match = re.match(pattern, stripped, flags=re.IGNORECASE)
            if match:
                command = str(match.group(1) or "").strip()
                if command:
                    return command

        return None

    def _match_run_python_request(self, text: str) -> Optional[str]:
        stripped = str(text or "").strip()

        patterns = [
            r"^(?:run|execute)\s+python\s+file\s+(.+\.py)$",
            r"^(?:run|execute)\s+(.+\.py)$",
            r"^python\s+(.+\.py)$",
        ]

        for pattern in patterns:
            match = re.match(pattern, stripped, flags=re.IGNORECASE)
            if match:
                path = str(match.group(1) or "").strip()
                if path:
                    return path

        return None

    def _match_create_empty_file_request(self, text: str) -> Optional[str]:
        stripped = str(text or "").strip()

        patterns = [
            r"^(?:create|make|ensure)\s+file\s+(.+)$",
            r"^(?:create|make|ensure)\s+an?\s+empty\s+file\s+(.+)$",
        ]

        for pattern in patterns:
            match = re.match(pattern, stripped, flags=re.IGNORECASE)
            if not match:
                continue

            raw_path = str(match.group(1) or "").strip()
            path = self._normalize_requested_path(raw_path)
            if path:
                return path

        return None

    def _match_write_file_request(self, text: str) -> Optional[Dict[str, str]]:
        stripped = str(text or "").strip()

        patterns = [
            r"^(?:write|create|make)\s+file\s+(.+?)\s+with\s+content\s+(.+)$",
            r"^(?:write|create|make)\s+(.+?)\s+with\s+content\s+(.+)$",
            r"^(?:write|save)\s+(.+?)\s+to\s+(.+)$",
        ]

        for pattern in patterns:
            match = re.match(pattern, stripped, flags=re.IGNORECASE)
            if not match:
                continue

            left = str(match.group(1) or "").strip()
            right = str(match.group(2) or "").strip()

            if " to " in stripped.lower() and pattern.endswith(r"\s+to\s+(.+)$"):
                content = left
                path = self._normalize_requested_path(right)
            else:
                path = self._normalize_requested_path(left)
                content = self._strip_wrapping_quotes(right)

            if path and content != "":
                return {
                    "path": path,
                    "content": content,
                }

        return None

    def _match_write_into_existing_request(self, text: str, last_path: Optional[str]) -> Optional[Dict[str, str]]:
        stripped = str(text or "").strip()

        patterns = [
            r"^(?:write|save)\s+(.+)$",
            r"^(?:put)\s+(.+)\s+into\s+file$",
        ]

        for pattern in patterns:
            match = re.match(pattern, stripped, flags=re.IGNORECASE)
            if not match:
                continue

            content = self._strip_wrapping_quotes(str(match.group(1) or "").strip())
            if content and last_path:
                return {
                    "path": last_path,
                    "content": content,
                }

        return None

    def _normalize_requested_path(self, raw_path: str) -> str:
        candidate = self._strip_wrapping_quotes(str(raw_path or "").strip())
        candidate = candidate.replace("\\", "/").strip()

        if not candidate:
            return ""

        if candidate.startswith("workspace/") or candidate.startswith("shared/") or candidate.startswith("sandbox/"):
            return candidate

        if re.match(r"^[A-Za-z]:/", candidate):
            return candidate

        if "/" in candidate:
            return candidate

        return f"workspace/shared/{candidate}"

    def _strip_wrapping_quotes(self, text: str) -> str:
        value = str(text or "").strip()
        if len(value) >= 2:
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                return value[1:-1]
        return value

    def _looks_like_file_candidate(self, value: str) -> bool:
        lowered = str(value or "").strip().lower()
        return lowered.endswith((".txt", ".md", ".json", ".log", ".csv"))

    # ============================================================
    # result builder / contract normalization
    # ============================================================

    def _build_plan_result(
        self,
        steps: List[Dict[str, Any]],
        intent: str,
        final_answer: str,
        fallback_used: bool,
        error: Optional[str],
    ) -> Dict[str, Any]:
        normalized_steps = self._normalize_steps(steps)

        result = {
            "ok": error is None,
            "planner_mode": self.PLANNER_MODE,
            "intent": str(intent or "respond"),
            "final_answer": str(final_answer or ""),
            "steps": normalized_steps,
            "error": error,
            "meta": {
                "fallback_used": bool(fallback_used),
                "step_count": len(normalized_steps),
            },
        }

        return result

    def _normalize_steps(self, steps: Any) -> List[Dict[str, Any]]:
        if not isinstance(steps, list):
            return []

        normalized: List[Dict[str, Any]] = []
        fallback_task_name = self._infer_task_name(task_dir="", goal="planner_steps")

        for idx, step in enumerate(steps, start=1):
            normalized.append(
                self._normalize_step(
                    step=step,
                    index=idx,
                    fallback_task_name=fallback_task_name,
                )
            )

        return normalized

    def _normalize_step(
        self,
        step: Any,
        index: int,
        fallback_task_name: str,
    ) -> Dict[str, Any]:
        if isinstance(step, dict):
            item = dict(step)
        else:
            item = {"type": "unknown", "value": step}

        step_type = str(item.get("type") or "unknown").strip() or "unknown"
        task_name = str(item.get("task_name") or fallback_task_name).strip() or fallback_task_name
        step_id = str(item.get("id") or f"{task_name}_step_{index}").strip() or f"{task_name}_step_{index}"

        normalized = dict(item)
        normalized["type"] = step_type
        normalized["task_name"] = task_name
        normalized["id"] = step_id

        if step_type in {"read_file", "write_file", "ensure_file", "run_python", "verify_file"}:
            normalized["path"] = str(normalized.get("path") or "")

        if step_type == "command":
            normalized["command"] = str(normalized.get("command") or "")

        if step_type == "web_search":
            normalized["query"] = str(normalized.get("query") or "")

        if step_type == "llm":
            normalized["prompt"] = str(normalized.get("prompt") or "")
            normalized["mode"] = str(normalized.get("mode") or "")

        if step_type == "write_file":
            normalized["content"] = str(normalized.get("content") or "")
            normalized["scope"] = str(normalized.get("scope") or self._infer_path_scope(normalized.get("path", "")))

        if step_type == "ensure_file":
            normalized["scope"] = str(normalized.get("scope") or self._infer_path_scope(normalized.get("path", "")))

        return normalized

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
        _ = task_dir
        safe_goal = str(goal or "task")
        return "task_" + hashlib.sha1(safe_goal.encode("utf-8")).hexdigest()[:6]

    def _apply_step_metadata(self, steps: List[Dict[str, Any]], task_name: str) -> List[Dict[str, Any]]:
        enriched: List[Dict[str, Any]] = []

        for idx, step in enumerate(steps, start=1):
            item = dict(step or {})
            item.setdefault("id", f"{task_name}_step_{idx}")
            item.setdefault("task_name", task_name)
            item.setdefault("type", "unknown")
            enriched.append(item)

        return enriched

    def _infer_intent(self, text: str, route: Any, steps: List[Dict[str, Any]]) -> str:
        _ = text
        _ = route

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