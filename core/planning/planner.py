from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple

from core.runtime.trace_logger import ensure_trace_logger


class Planner:
    """
    Deterministic Planner v18

    修正重點：
    1. 保留 deterministic planner 規則優先順序
    2. 保留跨子句 last_path 記憶
    3. 支援「先建立檔案，然後再讀出來」這種多步語句
    4. 第二句若是 read 但未明講檔名，會優先沿用上一句檔案路徑
    5. 沒有明確內容時，不再產生 write_file 覆蓋檔案，改為 ensure_file
    6. 修正空內容誤判問題，避免 write_file(path, "") 洗掉原本內容
    7. 保留 trace logger 與 run() 相容入口

    規則優先順序：
    1. command
    2. write / ensure_file
    3. read
    4. search
    5. fallback -> llm_generate
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
            print("### USING PLANNER v18 (ENSURE_FILE + EMPTY-CONTENT FIX) ###")
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
            },
        )

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

        try:
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
    # core planning
    # ============================================================

    def _plan_steps(self, text: str, route: Any = None) -> Tuple[List[Dict[str, Any]], bool]:
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

        # 1. command 優先
        cmd = self._extract_command(stripped)
        if cmd:
            self.trace_logger.log_decision(
                title="command detected",
                message=cmd,
                source="planner",
            )
            return [{"type": "command", "command": cmd}], False, last_path

        # 2. write / ensure_file 優先於 read
        write = self._extract_write_request(stripped)
        if write:
            current_path = str(write.get("path") or "").strip() or last_path
            content = write.get("content", "")
            has_explicit_content = bool(write.get("has_explicit_content", False))

            if has_explicit_content:
                normalized_step = {
                    "type": "write_file",
                    "path": current_path or "",
                    "content": content,
                }
                step_type = "write detected"
            else:
                normalized_step = {
                    "type": "ensure_file",
                    "path": current_path or "",
                }
                step_type = "ensure_file detected"

            self.trace_logger.log_decision(
                title=step_type,
                message=normalized_step.get("path", ""),
                source="planner",
                raw=normalized_step,
            )
            return [normalized_step], False, current_path

        # 3. read
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

        # 4. search
        if self._looks_like_search(stripped):
            self.trace_logger.log_decision(
                title="search detected",
                message=stripped,
                source="planner",
            )
            return [{"type": "web_search", "query": stripped}], False, last_path

        # 5. fallback
        self.trace_logger.log_decision(
            title="fallback detected",
            message=stripped,
            source="planner",
            raw={
                "reason": "no deterministic rule matched",
                "last_path": last_path,
            },
        )
        return [{"type": "llm_generate", "prompt": stripped}], True, last_path

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
            "planner_mode": "deterministic_v18",
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
    # command
    # ============================================================

    def _extract_command(self, text: str) -> Optional[str]:
        lowered = text.lower().strip()
        if lowered.startswith(("python ", "python3 ", "cmd ", "powershell ", "py ")):
            return text.strip()
        return None

    # ============================================================
    # path / read / write
    # ============================================================

    def _extract_file_path(self, text: str) -> Optional[str]:
        patterns = [
            r"([A-Za-z0-9_\-./\\]+?\.(?:py|txt|md|json|yaml|yml|csv|log))",
        ]

        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                return m.group(1).strip()

        return None

    def _looks_like_read(self, text: str) -> bool:
        lowered = text.lower()
        keywords = [
            "讀取",
            "讀出來",
            "讀一下",
            "查看",
            "read",
            "open",
            "看一下",
            "檢查",
            "打開",
            "顯示內容",
            "show content",
        ]
        return any(k in lowered for k in keywords)

    def _resolve_read_path(self, text: str, last_path: Optional[str]) -> Optional[str]:
        explicit_path = self._extract_file_path(text)
        if explicit_path:
            return explicit_path

        lowered = text.lower().strip()

        implicit_read_markers = [
            "再讀出來",
            "讀出來",
            "把它讀出來",
            "把他讀出來",
            "把檔案讀出來",
            "把那個讀出來",
            "再讀",
            "讀一下",
            "看一下",
            "打開它",
            "打開",
            "查看內容",
            "read it",
            "open it",
            "show it",
        ]

        if last_path and any(marker in lowered for marker in implicit_read_markers):
            return last_path

        if last_path and self._looks_like_read(text):
            return last_path

        return None

    def _extract_write_request(self, text: str) -> Optional[Dict[str, Any]]:
        lowered = text.lower()

        has_write_intent = any(k in text for k in ["寫", "建立", "新增", "創建", "產生"]) or any(
            k in lowered for k in ["create", "write", "make", "generate"]
        )
        if not has_write_intent:
            return None

        path = self._extract_file_path(text)
        if not path:
            return None

        content, has_explicit_content = self._extract_write_content(text)
        return {
            "path": path,
            "content": content,
            "has_explicit_content": has_explicit_content,
        }

    def _extract_write_content(self, text: str) -> Tuple[str, bool]:
        stripped = str(text or "").strip()

        patterns = [
            r"內容是\s*(.+)$",
            r"內容為\s*(.+)$",
            r"內容:\s*(.+)$",
            r"內容：\s*(.+)$",
            r"寫入\s*(.+)$",
            r"內容放\s*(.+)$",
            r"with content\s+(.+)$",
            r"content is\s+(.+)$",
            r"content:\s*(.+)$",
            r"寫成\s*(.+)$",
        ]

        # 明確匹配內容
        for pattern in patterns:
            m = re.search(pattern, stripped, flags=re.IGNORECASE)
            if m:
                raw = m.group(1).strip()
                if raw:
                    return self._normalize_special_content(self._strip_quotes(raw)), True

        # fallback：檔名後面若真的還有內容才算 explicit
        file_path = self._extract_file_path(stripped)
        if file_path:
            idx = stripped.find(file_path)
            if idx >= 0:
                tail = stripped[idx + len(file_path):].strip()

                if tail:
                    tail = re.sub(
                        r"^(內容是|內容為|內容|寫入|寫成)\s*",
                        "",
                        tail,
                        flags=re.IGNORECASE,
                    ).strip()

                    if tail:
                        return self._normalize_special_content(self._strip_quotes(tail)), True

        return "", False

    def _normalize_special_content(self, text: str) -> str:
        value = str(text or "").strip()

        special_map = {
            "今天日期": "{{CURRENT_DATE}}",
            "今日日期": "{{CURRENT_DATE}}",
            "今天的日期": "{{CURRENT_DATE}}",
            "today date": "{{CURRENT_DATE}}",
            "today's date": "{{CURRENT_DATE}}",
        }

        lowered = value.lower()
        for key, mapped in special_map.items():
            if lowered == key.lower():
                return mapped

        return value

    def _strip_quotes(self, text: str) -> str:
        value = str(text or "").strip()
        quote_pairs = {
            "'": "'",
            '"': '"',
            "「": "」",
            "“": "”",
        }

        if len(value) >= 2:
            first = value[0]
            last = value[-1]
            if first in quote_pairs and quote_pairs[first] == last:
                return value[1:-1].strip()

        return value

    # ============================================================
    # search
    # ============================================================

    def _looks_like_search(self, text: str) -> bool:
        lowered = text.lower()
        return any(k in lowered for k in ["搜尋", "search", "查詢", "查找"])

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
        if steps:
            return steps[0].get("type", "unknown")
        return "respond"