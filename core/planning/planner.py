from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple

from core.runtime.trace_logger import ensure_trace_logger


class Planner:
    """
    Deterministic Planner v26

    本版重點：
    1. 保留 document flow 偵測
    2. 保留 command / write / ensure / read / search 規則
    3. 保留 run_python 規則
    4. 保留 verify 規則
    5. verify 類句型先於 document flow 判定
    6. 修正 action_items / summary task 句型優先序：
       - task summarize input.txt into summary.txt
       - task read input.txt and extract action items into action_items.txt
       這類 task goal 不再被一般 read_file 規則提前吃掉
    7. 修正 document flow 固定寫死 input.txt / summary.txt / action_items.txt 的問題：
       - 保留使用者指定的 source path
       - 保留使用者指定的 output path
       - 支援 workspace/shared/...、shared/...、任意 *.txt / *.md / *.log / *.json 等路徑
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
            print("### USING PLANNER v26 (DOCUMENT FLOW PRESERVE USER PATHS) ###")
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

        # --------------------------------------------------------
        # verify routing first
        # 目的：避免 verify ... exists/contains/equals 被 document flow 吃掉
        # --------------------------------------------------------
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

    def _normalize_document_flow_text(self, text: str) -> str:
        lowered = str(text or "").strip().lower()

        prefixes = [
            "task ",
            "create task ",
            "new task ",
            "submit task ",
            "please ",
            "pls ",
        ]
        changed = True
        while changed:
            changed = False
            for prefix in prefixes:
                if lowered.startswith(prefix):
                    lowered = lowered[len(prefix):].strip()
                    changed = True

        return lowered

    def _plan_document_flow(self, text: str) -> Optional[List[Dict[str, Any]]]:
        lowered = self._normalize_document_flow_text(text)
        all_paths = self._extract_all_file_paths(text)

        explicit_source = self._extract_document_source_path(text, all_paths)
        explicit_output = self._extract_document_output_path(text, all_paths)

        explicit_action_patterns = [
            r"read\s+.+?\s+and\s+extract\s+action\s+items\s+into\s+.+",
            r"extract\s+action\s+items\s+from\s+.+?\s+into\s+.+",
            r"extract\s+action\s+items\s+into\s+.+?\s+from\s+.+",
            r".+?\s*->\s*.+",
        ]
        explicit_summary_patterns = [
            r"read\s+.+?\s+and\s+summari[sz]e\s+(?:it\s+)?into\s+.+",
            r"summari[sz]e\s+.+?\s+into\s+.+",
            r"summary\s+.+?\s+into\s+.+",
            r".+?\s*->\s*.+",
        ]

        action_keywords = [
            "action item",
            "action items",
            "extract action items",
            "todo",
            "to-do",
            "行動項目",
            "待辦事項",
        ]
        summary_keywords = [
            "summary",
            "summarize",
            "summarise",
            "摘要",
            "總結",
        ]

        wants_action_items = any(k in lowered for k in action_keywords)
        wants_summary = any(k in lowered for k in summary_keywords)

        if wants_action_items:
            source_path = explicit_source or self._choose_default_document_source(all_paths) or "input.txt"
            output_path = explicit_output or self._choose_default_action_items_output(all_paths) or "action_items.txt"

            if self._looks_like_document_flow_request(text):
                return self._build_action_items_steps(source_path, output_path)

            for pattern in explicit_action_patterns:
                if re.search(pattern, lowered):
                    return self._build_action_items_steps(source_path, output_path)

        if wants_summary:
            source_path = explicit_source or self._choose_default_document_source(all_paths) or "input.txt"
            output_path = explicit_output or self._choose_default_summary_output(all_paths) or "summary.txt"

            if self._looks_like_document_flow_request(text):
                return self._build_summary_steps(source_path, output_path)

            for pattern in explicit_summary_patterns:
                if re.search(pattern, lowered):
                    return self._build_summary_steps(source_path, output_path)

        # 關鍵：input.txt / summary.txt / action_items.txt 舊型固定流程仍支援
        has_input_txt = "input.txt" in lowered
        has_action_items_txt = "action_items.txt" in lowered
        has_summary_txt = "summary.txt" in lowered

        if has_input_txt and (wants_action_items or has_action_items_txt):
            return self._build_action_items_steps("input.txt", explicit_output or "action_items.txt")

        if has_input_txt and (wants_summary or has_summary_txt):
            return self._build_summary_steps("input.txt", explicit_output or "summary.txt")

        return None

    def _looks_like_document_flow_request(self, text: str) -> bool:
        lowered = self._normalize_document_flow_text(text)
        doc_markers = [
            "read ",
            "summarize ",
            "summarise ",
            "summary ",
            "extract action items",
            "action items",
            "摘要",
            "總結",
            "行動項目",
            "待辦事項",
            "into ",
            "from ",
            "->",
        ]
        return any(marker in lowered for marker in doc_markers)

    def _extract_document_source_path(self, text: str, all_paths: List[str]) -> Optional[str]:
        stripped = str(text or "").strip()

        patterns = [
            r"\bfrom\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
            r"\bread\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
            r"\bsummari[sz]e\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
            r"\bsummary\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
            r"\bextract\s+action\s+items\s+from\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
        ]

        for pattern in patterns:
            m = re.search(pattern, stripped, flags=re.IGNORECASE)
            if m:
                value = str(m.group(1)).strip()
                if value:
                    return value

        arrow = self._extract_arrow_paths(stripped)
        if arrow is not None:
            source_path, _ = arrow
            return source_path

        if all_paths:
            return all_paths[0]

        return None

    def _extract_document_output_path(self, text: str, all_paths: List[str]) -> Optional[str]:
        stripped = str(text or "").strip()

        patterns = [
            r"\binto\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
            r"\bto\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
            r"\bwrite\s+.+?\s+to\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
            r"\boutput\s+to\s+([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\b",
        ]

        for pattern in patterns:
            m = re.search(pattern, stripped, flags=re.IGNORECASE)
            if m:
                value = str(m.group(1)).strip()
                if value:
                    return value

        arrow = self._extract_arrow_paths(stripped)
        if arrow is not None:
            _, output_path = arrow
            return output_path

        if len(all_paths) >= 2:
            return all_paths[-1]

        return None

    def _extract_arrow_paths(self, text: str) -> Optional[Tuple[str, str]]:
        stripped = str(text or "").strip()
        m = re.search(
            r"([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\s*->\s*([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))",
            stripped,
            flags=re.IGNORECASE,
        )
        if not m:
            return None

        source_path = str(m.group(1)).strip()
        output_path = str(m.group(2)).strip()
        if not source_path or not output_path:
            return None

        return source_path, output_path

    def _extract_all_file_paths(self, text: str) -> List[str]:
        if not text:
            return []

        results: List[str] = []
        pattern = r"\b([A-Za-z0-9_\-./\\]+?\.(?:py|txt|md|json|yaml|yml|csv|log))\b"
        for m in re.finditer(pattern, text):
            value = str(m.group(1)).strip()
            if value and value not in results:
                results.append(value)
        return results

    def _choose_default_document_source(self, all_paths: List[str]) -> Optional[str]:
        for path in all_paths:
            lowered = path.lower()
            if lowered.endswith((".txt", ".md", ".log", ".json", ".csv", ".yaml", ".yml")):
                return path
        return None

    def _choose_default_summary_output(self, all_paths: List[str]) -> Optional[str]:
        for path in all_paths:
            lowered = path.lower()
            if "summary" in lowered:
                return path
        return None

    def _choose_default_action_items_output(self, all_paths: List[str]) -> Optional[str]:
        for path in all_paths:
            lowered = path.lower()
            if "action_items" in lowered or "action-items" in lowered or "actionitems" in lowered:
                return path
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
            "planner_mode": "deterministic_v26",
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
    # run_python
    # ============================================================

    def _extract_run_python_request(self, text: str) -> Optional[Dict[str, Any]]:
        stripped = str(text or "").strip()
        lowered = stripped.lower()

        file_path = self._extract_file_path(stripped)
        if not file_path or not file_path.lower().endswith(".py"):
            return None

        run_markers = [
            "run python file",
            "run python script",
            "run file",
            "execute python file",
            "execute python script",
            "execute file",
            "執行 python",
            "執行python",
            "執行檔案",
            "執行腳本",
            "跑 python",
            "跑python",
            "運行 python",
            "run ",
            "execute ",
        ]

        if any(marker in lowered for marker in run_markers):
            return {
                "type": "run_python",
                "path": file_path,
            }

        return None

    # ============================================================
    # verify
    # ============================================================

    def _extract_verify_request(self, text: str, last_path: Optional[str]) -> Optional[Dict[str, Any]]:
        stripped = str(text or "").strip()
        lowered = stripped.lower()

        verify_markers = [
            "verify",
            "check that",
            "confirm that",
            "確認",
            "檢查",
            "驗證",
        ]
        if not any(marker in lowered for marker in verify_markers):
            return None

        path = self._extract_file_path(stripped) or last_path

        exists_match = re.search(
            r"(?:verify|check that|confirm that)\s+(.+?)\s+exists\b",
            lowered,
            flags=re.IGNORECASE,
        )
        if exists_match and path:
            return {
                "type": "verify",
                "path": path,
                "exists": True,
            }

        not_exists_match = re.search(
            r"(?:verify|check that|confirm that)\s+(.+?)\s+does not exist\b",
            lowered,
            flags=re.IGNORECASE,
        )
        if not_exists_match and path:
            return {
                "type": "verify",
                "path": path,
                "exists": False,
            }

        contains_match = re.search(
            r"(?:contains|contain)\s+(.+)$",
            stripped,
            flags=re.IGNORECASE,
        )
        if contains_match and path:
            raw = contains_match.group(1).strip()
            raw = self._strip_quotes(raw)
            if raw:
                return {
                    "type": "verify",
                    "path": path,
                    "contains": raw,
                }

        equals_match = re.search(
            r"(?:equals|equal to|is exactly)\s+(.+)$",
            stripped,
            flags=re.IGNORECASE,
        )
        if equals_match and path:
            raw = equals_match.group(1).strip()
            raw = self._strip_quotes(raw)
            if raw:
                return {
                    "type": "verify",
                    "path": path,
                    "equals": raw,
                }

        zh_exists = any(k in stripped for k in ["存在", "有沒有", "是否存在"])
        if zh_exists and path:
            return {
                "type": "verify",
                "path": path,
                "exists": True,
            }

        zh_contains_match = re.search(r"(?:包含|含有)\s+(.+)$", stripped)
        if zh_contains_match and path:
            raw = zh_contains_match.group(1).strip()
            raw = self._strip_quotes(raw)
            if raw:
                return {
                    "type": "verify",
                    "path": path,
                    "contains": raw,
                }

        zh_equals_match = re.search(r"(?:等於|是否為|是不是|是否等於)\s+(.+)$", stripped)
        if zh_equals_match and path:
            raw = zh_equals_match.group(1).strip()
            raw = self._strip_quotes(raw)
            if raw:
                return {
                    "type": "verify",
                    "path": path,
                    "equals": raw,
                }

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

        if self._extract_run_python_request(text):
            return None

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