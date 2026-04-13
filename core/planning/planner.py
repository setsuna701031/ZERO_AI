from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple

from core.runtime.trace_logger import ensure_trace_logger


class Planner:
    """
    Deterministic Planner v22

    本版重點：
    1. 強化 document flow 偵測：
       - read input.txt and extract action items into action_items.txt
       - summarize input.txt into summary.txt
       - input.txt -> action_items.txt
       - input.txt -> summary.txt
    2. 修正 read path 誤吞整句問題
    3. fallback 一律使用 llm
    4. document flow 輸出檔固定寫到 shared，避免 single-shot 沒 task_id 時炸掉
    5. 升級 action-items prompt，強化 due date/time 抽取品質
    6. 保留原本 command / write / ensure / read / search 規則
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
            print("### USING PLANNER v22 (ACTION ITEMS PROMPT UPGRADE) ###")
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
        stripped = str(text or "").strip()

        special_document_steps = self._plan_document_flow(stripped)
        if special_document_steps is not None:
            self.trace_logger.log_decision(
                title="document flow detected",
                message=stripped,
                source="planner",
                raw={"steps": special_document_steps},
            )
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
        lowered = str(text or "").strip().lower()

        explicit_action_patterns = [
            r"read\s+input\.txt\s+and\s+extract\s+action\s+items\s+into\s+action_items\.txt",
            r"extract\s+action\s+items\s+from\s+input\.txt\s+into\s+action_items\.txt",
            r"input\.txt\s*->\s*action_items\.txt",
        ]
        for pattern in explicit_action_patterns:
            if re.search(pattern, lowered):
                return self._build_action_items_steps("input.txt", "action_items.txt")

        explicit_summary_patterns = [
            r"read\s+input\.txt\s+and\s+summari[sz]e\s+(?:it\s+)?into\s+summary\.txt",
            r"summari[sz]e\s+input\.txt\s+into\s+summary\.txt",
            r"input\.txt\s*->\s*summary\.txt",
        ]
        for pattern in explicit_summary_patterns:
            if re.search(pattern, lowered):
                return self._build_summary_steps("input.txt", "summary.txt")

        has_input_txt = "input.txt" in lowered
        has_action_items_txt = "action_items.txt" in lowered
        has_summary_txt = "summary.txt" in lowered

        action_keywords = [
            "action item",
            "action items",
            "extract action items",
            "todo",
            "to-do",
            "meeting notes",
            "行動項目",
            "待辦事項",
            "會議紀錄",
        ]
        summary_keywords = [
            "summary",
            "summarize",
            "summarise",
            "摘要",
            "總結",
        ]

        wants_action_items = any(k in lowered for k in action_keywords) or has_action_items_txt
        wants_summary = any(k in lowered for k in summary_keywords) or has_summary_txt

        if has_input_txt and wants_action_items:
            return self._build_action_items_steps("input.txt", "action_items.txt")

        if has_input_txt and wants_summary:
            return self._build_summary_steps("input.txt", "summary.txt")

        if wants_action_items:
            return self._build_action_items_steps("input.txt", "action_items.txt")

        if wants_summary and ("txt" in lowered or "document" in lowered or "文件" in lowered or "檔案" in lowered):
            return self._build_summary_steps("input.txt", "summary.txt")

        return None

    def _build_action_items_steps(self, source_path: str, output_path: str) -> List[Dict[str, Any]]:
        prompt_template = (
            "You are an assistant that extracts action items from notes.\n\n"
            "Read the document content below and produce a clean plain-text file.\n\n"
            "Output rules:\n"
            "1. Output title must be exactly: ACTION ITEMS\n"
            "2. For each item use exactly this format:\n"
            "   1. Owner: <name or Unassigned>\n"
            "      Task: <clear action>\n"
            "      Due: <deadline or Not specified>\n"
            "3. If no explicit owner, use Unassigned.\n"
            "4. If no explicit deadline or time commitment for the action, use Not specified.\n"
            "5. Do not output JSON.\n"
            "6. Do not add explanations before or after the list.\n"
            "7. Only include real action items. Do not include pure status statements or background facts.\n\n"
            "Due extraction rules:\n"
            "- Preserve explicit due phrases when they belong to the action, such as:\n"
            "  by Monday, by Friday, today, tomorrow, this afternoon, this evening, next week, next month.\n"
            "- If a sentence says someone will do something by a certain day, keep that due phrase.\n"
            "- If a sentence describes a past event, such as last night, yesterday, previously, do not treat that as a due date unless it clearly applies to the action.\n"
            "- Prefer the deadline phrase exactly as written in the notes when reasonable.\n"
            "- If the time phrase belongs to the action, keep it in Due.\n"
            "- If there is no due phrase for the action, write Not specified.\n\n"
            "Owner extraction rules:\n"
            "- Use a person's name when explicitly stated.\n"
            "- For group statements like 'we should', use Unassigned unless a real owner is named.\n\n"
            "Task extraction rules:\n"
            "- Rewrite each task as a short, clear action.\n"
            "- Do not copy unnecessary background context into Task unless it is needed for clarity.\n\n"
            "Document content:\n"
            "{{file_content}}\n"
        )

        return [
            {
                "type": "read_file",
                "path": source_path,
            },
            {
                "type": "llm",
                "mode": "action_items",
                "prompt_template": prompt_template,
            },
            {
                "type": "write_file",
                "path": output_path,
                "scope": "shared",
                "use_previous_text": True,
            },
        ]

    def _build_summary_steps(self, source_path: str, output_path: str) -> List[Dict[str, Any]]:
        prompt_template = (
            "Summarize the following document into a concise plain-text summary.\n\n"
            "Rules:\n"
            "1. Keep it clear and short.\n"
            "2. Do not use JSON.\n"
            "3. Do not add extra commentary.\n\n"
            "Document content:\n"
            "{{file_content}}\n"
        )

        return [
            {
                "type": "read_file",
                "path": source_path,
            },
            {
                "type": "llm",
                "mode": "summary",
                "prompt_template": prompt_template,
            },
            {
                "type": "write_file",
                "path": output_path,
                "scope": "shared",
                "use_previous_text": True,
            },
        ]

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
            "planner_mode": "deterministic_v22",
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
        if not text:
            return None

        patterns = [
            r"\b([A-Za-z0-9_\-./\\]+?\.(?:py|txt|md|json|yaml|yml|csv|log))\b",
        ]

        candidates: List[str] = []
        for pattern in patterns:
            for m in re.finditer(pattern, text):
                value = str(m.group(1)).strip()
                if value:
                    candidates.append(value)

        if not candidates:
            return None

        return candidates[0]

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

        for pattern in patterns:
            m = re.search(pattern, stripped, flags=re.IGNORECASE)
            if m:
                raw = m.group(1).strip()
                if raw:
                    return self._normalize_special_content(self._strip_quotes(raw)), True

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