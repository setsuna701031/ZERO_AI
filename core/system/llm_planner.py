from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple


class LLMPlanner:
    """
    LLM Brain / LLM Planner v4

    修正版目標：
    1. 保留 LLM JSON 規劃能力
    2. 在進 LLM 前，先走 deterministic guard，避免明確檔案操作被 LLM 誤判
    3. 支援 ensure_file，避免「建立但沒內容」被轉成 write_file(path, "")
    4. 支援多子句：例如「幫我建立一個 a.txt，然後再讀出來」
    5. 支援跨子句 last_path 記憶
    6. 保留 summary / action-items document flow deterministic guard
    7. 保留使用者指定的 source / output path
    8. 新增 requirement-pack deterministic guard
    """

    def __init__(
        self,
        llm_client: Any,
        debug: bool = False,
        max_steps: int = 5,
    ) -> None:
        self.llm_client = llm_client
        self.debug = debug
        self.max_steps = max_steps



    def _effective_max_steps(self, steps: List[Dict[str, Any]]) -> int:
        if not isinstance(steps, list):
            return self.max_steps

        if any(str(step.get("path") or "").strip().lower() == "project_summary.txt" for step in steps if isinstance(step, dict)):
            return max(self.max_steps, len(steps))

        return self.max_steps

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

        if not text:
            return self._build_result(
                ok=True,
                intent="respond",
                final_answer="空白輸入",
                steps=[],
                error=None,
                fallback_used=False,
                reason="empty input",
            )

        deterministic = self._plan_deterministic(text=text)
        if deterministic is not None:
            return deterministic

        if self.llm_client is None:
            return self._build_result(
                ok=False,
                intent="respond",
                final_answer="LLM client missing",
                steps=[],
                error="llm_client missing",
                fallback_used=True,
                reason="llm client missing",
            )

        prompt = self._build_prompt(
            user_input=text,
            context=context,
            route=route,
        )

        raw = self._call_llm(prompt)
        if self.debug:
            print("[LLMPlanner] raw =", raw)

        parsed = self._parse_llm_json(raw)
        if self.debug:
            print("[LLMPlanner] parsed =", parsed)

        if not isinstance(parsed, dict):
            return self._build_result(
                ok=False,
                intent="respond",
                final_answer="LLM planner parse failed",
                steps=[],
                error="llm planner parse failed",
                fallback_used=True,
                reason="invalid json output",
            )

        normalized = self._normalize_plan(parsed, fallback_text=text)
        return normalized

    def run(self, *args, **kwargs):
        return self.plan(*args, **kwargs)

    # ============================================================
    # deterministic guard
    # ============================================================

    def _plan_deterministic(self, text: str) -> Optional[Dict[str, Any]]:
        document_steps = self._plan_document_flow(text)
        if document_steps is not None:
            intent = self._infer_document_intent(document_steps)
            return self._build_result(
                ok=True,
                intent=intent,
                final_answer=f"已規劃 {len(document_steps)} 個步驟",
                steps=document_steps[: self._effective_max_steps(document_steps)],
                error=None,
                fallback_used=False,
                reason="document flow deterministic guard matched",
            )

        clauses = self._split_clauses(text)
        if not clauses:
            return None

        steps: List[Dict[str, Any]] = []
        last_path: Optional[str] = None

        for clause in clauses:
            clause_steps, last_path = self._plan_single_clause(clause, last_path=last_path)
            if clause_steps is None:
                return None
            steps.extend(clause_steps)

        if not steps:
            return None

        intent = str(steps[0].get("type", "respond") or "respond").strip()

        return self._build_result(
            ok=True,
            intent=intent,
            final_answer=f"已規劃 {len(steps)} 個步驟",
            steps=steps[: self._effective_max_steps(steps)],
            error=None,
            fallback_used=False,
            reason="deterministic guard matched",
        )

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

        requirement_pack = self._extract_requirement_pack_request(text, all_paths)
        if requirement_pack is not None:
            source_path = requirement_pack.get("input_file") or "requirement.txt"
            return self._build_requirement_pack_steps(source_path)

        if wants_summary:
            source_path = explicit_source or self._choose_default_document_source(all_paths) or "input.txt"
            output_path = explicit_output or self._choose_default_summary_output(all_paths) or "summary.txt"

            if self._looks_like_document_flow_request(text):
                return self._build_summary_steps(source_path, output_path)

        # 舊型固定流程仍支援，但 output 仍優先保留使用者指定值
        has_input_txt = "input.txt" in lowered
        has_action_items_txt = "action_items.txt" in lowered
        has_summary_txt = "summary.txt" in lowered

        if has_input_txt and (wants_action_items or has_action_items_txt):
            return self._build_action_items_steps(
                explicit_source or "input.txt",
                explicit_output or "action_items.txt",
            )

        if has_input_txt and (wants_summary or has_summary_txt):
            return self._build_summary_steps(
                explicit_source or "input.txt",
                explicit_output or "summary.txt",
            )

        return None

    def _extract_requirement_pack_request(self, text: str, all_paths: List[str]) -> Optional[Dict[str, str]]:
        stripped = str(text or "").strip()
        lowered = self._normalize_document_flow_text(text)

        requirement_markers = [
            "requirement",
            "requirements",
            "spec",
            "specification",
            "需求",
            "需求書",
        ]
        output_markers = [
            "project_summary.txt",
            "implementation_plan.txt",
            "acceptance_checklist.txt",
        ]

        has_requirement_source = any(marker in lowered for marker in requirement_markers)
        has_requirement_outputs = all(marker in lowered for marker in output_markers)

        if not has_requirement_outputs:
            return None

        source_path = self._extract_document_source_path(stripped, all_paths)
        if not source_path:
            if has_requirement_source:
                source_path = "requirement.txt"
            else:
                return None

        return {
            "task_type": "document",
            "mode": "requirement_pack",
            "input_file": source_path,
        }

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
            "write ",
            "to ",
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
            match = re.search(pattern, stripped, flags=re.IGNORECASE)
            if match:
                value = str(match.group(1)).strip()
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
            match = re.search(pattern, stripped, flags=re.IGNORECASE)
            if match:
                value = str(match.group(1)).strip()
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
        match = re.search(
            r"([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))\s*->\s*([A-Za-z0-9_\-./\\]+?\.(?:txt|md|log|json|csv|yaml|yml))",
            stripped,
            flags=re.IGNORECASE,
        )
        if not match:
            return None

        source_path = str(match.group(1)).strip()
        output_path = str(match.group(2)).strip()
        if not source_path or not output_path:
            return None

        return source_path, output_path

    def _extract_all_file_paths(self, text: str) -> List[str]:
        if not text:
            return []

        results: List[str] = []
        pattern = r"\b([A-Za-z0-9_\-./\\]+?\.(?:py|txt|md|json|yaml|yml|csv|log))\b"
        for match in re.finditer(pattern, text):
            value = str(match.group(1)).strip()
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

    def _build_requirement_pack_steps(self, source_path: str) -> List[Dict[str, Any]]:
        summary_prompt = (
            "Read the requirement document below and produce a concise plain-text project summary.\n\n"
            "Required sections:\n"
            "1. Project Goal\n"
            "2. Key Requirements\n"
            "3. Constraints\n"
            "4. Expected Deliverables\n\n"
            "Rules:\n"
            "- Keep it clear and engineering-oriented.\n"
            "- Do not use JSON.\n"
            "- Do not add extra commentary outside the summary.\n\n"
            "Requirement document:\n"
            "{{file_content}}\n"
        )

        implementation_prompt = (
            "Read the requirement document below and produce a plain-text implementation plan.\n\n"
            "Required sections:\n"
            "1. Implementation Steps\n"
            "2. Recommended Execution Order\n"
            "3. Risks and Dependencies\n"
            "4. Verification Focus\n\n"
            "Rules:\n"
            "- Keep the plan practical and engineering-oriented.\n"
            "- Use numbered steps where useful.\n"
            "- Do not use JSON.\n"
            "- Do not add extra commentary outside the plan.\n\n"
            "Requirement document:\n"
            "{{file_content}}\n"
        )

        checklist_prompt = (
            "Read the requirement document below and produce a plain-text acceptance checklist.\n\n"
            "The output must contain exactly these section titles:\n"
            "Acceptance Criteria\n"
            "Verification\n"
            "Deliverable\n\n"
            "Rules:\n"
            "- Each section must contain concrete bullet points.\n"
            "- Keep it plain text.\n"
            "- Do not use JSON.\n"
            "- Do not add extra commentary outside the checklist.\n\n"
            "Requirement document:\n"
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
                "prompt_template": summary_prompt,
            },
            {
                "type": "write_file",
                "path": "project_summary.txt",
                "scope": "shared",
                "use_previous_text": True,
            },
            {
                "type": "llm",
                "mode": "summary",
                "prompt_template": implementation_prompt,
            },
            {
                "type": "write_file",
                "path": "implementation_plan.txt",
                "scope": "shared",
                "use_previous_text": True,
            },
            {
                "type": "llm",
                "mode": "summary",
                "prompt_template": checklist_prompt,
            },
            {
                "type": "write_file",
                "path": "acceptance_checklist.txt",
                "scope": "shared",
                "use_previous_text": True,
            },
            {
                "type": "verify",
                "path": "acceptance_checklist.txt",
                "scope": "shared",
                "contains": "Acceptance Criteria",
            },
            {
                "type": "verify",
                "path": "acceptance_checklist.txt",
                "scope": "shared",
                "contains": "Verification",
            },
            {
                "type": "verify",
                "path": "acceptance_checklist.txt",
                "scope": "shared",
                "contains": "Deliverable",
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

    def _infer_document_intent(self, steps: List[Dict[str, Any]]) -> str:
        if len(steps) >= 3:
            first_type = str(steps[0].get("type") or "").strip().lower()
            second_type = str(steps[1].get("type") or "").strip().lower()
            third_type = str(steps[2].get("type") or "").strip().lower()
            if first_type == "read_file" and second_type == "llm" and third_type == "write_file":
                llm_mode = str(steps[1].get("mode") or "").strip().lower()
                third_path = str(steps[2].get("path") or "").strip().lower()
                if llm_mode == "action_items":
                    return "action_items"
                if llm_mode == "summary" and third_path == "project_summary.txt":
                    return "requirement_pack"
                if llm_mode == "summary":
                    return "summary"
        if steps:
            return str(steps[0].get("type") or "respond").strip()
        return "respond"

    def _plan_single_clause(
        self,
        text: str,
        last_path: Optional[str] = None,
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        stripped = str(text or "").strip()
        if not stripped:
            return [], last_path

        command = self._extract_command(stripped)
        if command:
            return [{"type": "command", "command": command}], last_path

        write = self._extract_write_request(stripped)
        if write is not None:
            current_path = str(write.get("path") or "").strip() or (last_path or "")
            has_explicit_content = bool(write.get("has_explicit_content", False))
            content = str(write.get("content", "") or "")

            if not current_path:
                return None, last_path

            if has_explicit_content:
                return [
                    {
                        "type": "write_file",
                        "path": current_path,
                        "content": content,
                    }
                ], current_path

            return [
                {
                    "type": "ensure_file",
                    "path": current_path,
                }
            ], current_path

        if self._looks_like_read(stripped):
            read_path = self._resolve_read_path(stripped, last_path=last_path)
            if not read_path:
                return None, last_path
            return [{"type": "read_file", "path": read_path}], read_path

        if self._looks_like_search(stripped):
            return [{"type": "web_search", "query": stripped}], last_path

        if self._looks_like_pure_response(stripped):
            return [{"type": "respond", "message": stripped}], last_path

        return None, last_path

    # ============================================================
    # clause split
    # ============================================================

    def _split_clauses(self, text: str) -> List[str]:
        normalized = str(text or "").strip()

        parts = re.split(
            r"(?:，|,|。|；|;|\n+|\r\n+|然後|接著|之後|再來|再|and then|then)",
            normalized,
            flags=re.IGNORECASE,
        )
        return [p.strip() for p in parts if p and p.strip()]

    # ============================================================
    # low-level deterministic parsers
    # ============================================================

    def _extract_command(self, text: str) -> Optional[str]:
        lowered = text.lower().strip()
        if lowered.startswith(("python ", "python3 ", "py ", "cmd ", "powershell ")):
            return text.strip()
        return None

    def _extract_file_path(self, text: str) -> Optional[str]:
        patterns = [
            r"([A-Za-z0-9_\-./\\]+?\.(?:py|txt|md|json|yaml|yml|csv|log))",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()

        return None

    def _looks_like_read(self, text: str) -> bool:
        lowered = text.lower()
        keywords = [
            "讀取",
            "讀出來",
            "讀一下",
            "讀",
            "查看",
            "看一下",
            "看",
            "open",
            "read",
            "show content",
            "顯示內容",
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
            "看",
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

        has_write_intent = (
            any(k in text for k in ["寫", "建立", "新增", "創建", "產生"])
            or any(k in lowered for k in ["create", "write", "make", "generate"])
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
            match = re.search(pattern, stripped, flags=re.IGNORECASE)
            if match:
                raw = match.group(1).strip()
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

    def _looks_like_search(self, text: str) -> bool:
        lowered = text.lower()
        return any(k in lowered for k in ["搜尋", "search", "查詢", "查找"])

    def _looks_like_pure_response(self, text: str) -> bool:
        lowered = text.lower().strip()
        casual_markers = [
            "你好",
            "hello",
            "hi",
            "早安",
            "晚安",
            "謝謝",
            "thanks",
        ]
        return lowered in casual_markers

    # ============================================================
    # llm prompt / call
    # ============================================================

    def _build_prompt(
        self,
        user_input: str,
        context: Dict[str, Any],
        route: Any,
    ) -> str:
        safe_context = {
            "user_input": user_input,
            "route": route if isinstance(route, dict) else {},
            "memory_keys": list(context.keys()) if isinstance(context, dict) else [],
        }

        return f"""
You are the planning brain for a local AI agent system.

Your task:
- Understand the user's intent
- Produce a safe execution plan in STRICT JSON
- Prefer minimal steps
- Do not include explanations outside JSON
- If the user is only chatting or asking a question, return zero steps and provide final_answer
- If the user asks to read a file, use step type "read_file"
- If the user asks to write/create a file with explicit content, use step type "write_file"
- If the user asks to create/ensure a file without explicit content, use step type "ensure_file"
- If the user asks to search the web, use step type "web_search"
- If the user asks to run a command, use step type "command"
- If the request is ambiguous or unsafe to convert into steps, return zero steps and respond in final_answer

Allowed step types:
- read_file
- write_file
- ensure_file
- web_search
- command
- llm_generate
- respond

For write_file:
{{
  "type": "write_file",
  "path": "workspace/shared/hello.txt",
  "content": "hello"
}}

For ensure_file:
{{
  "type": "ensure_file",
  "path": "workspace/shared/hello.txt"
}}

For read_file:
{{
  "type": "read_file",
  "path": "workspace/shared/hello.txt"
}}

For web_search:
{{
  "type": "web_search",
  "query": "python dataclass tutorial"
}}

For command:
{{
  "type": "command",
  "command": "python app.py"
}}

For direct answer without tools:
{{
  "type": "respond",
  "message": "..."
}}

Return STRICT JSON with this exact shape:
{{
  "intent": "respond",
  "final_answer": "",
  "steps": []
}}

Rules:
- steps must be an array
- no markdown
- no comments
- no extra keys at top level besides: intent, final_answer, steps
- max {self.max_steps} steps
- if the user is speaking naturally and not clearly requesting files/commands/tools, prefer:
  {{"intent":"respond","final_answer":"...","steps":[]}}
- NEVER convert "create file without content" into write_file with empty content
- use ensure_file instead

Input:
{json.dumps(safe_context, ensure_ascii=False)}
""".strip()

    def _call_llm(self, prompt: str) -> str:
        if hasattr(self.llm_client, "generate_general"):
            data = self.llm_client.generate_general(prompt)
            if isinstance(data, dict):
                return str(data.get("response", "") or "")
            return str(data or "")

        if hasattr(self.llm_client, "chat_general"):
            return str(self.llm_client.chat_general(prompt) or "")

        if hasattr(self.llm_client, "generate"):
            data = self.llm_client.generate(prompt)
            if isinstance(data, dict):
                return str(data.get("response", "") or "")
            return str(data or "")

        if hasattr(self.llm_client, "chat"):
            return str(self.llm_client.chat(prompt) or "")

        return ""

    # ============================================================
    # parsing / normalize
    # ============================================================

    def _parse_llm_json(self, raw_text: str) -> Optional[Dict[str, Any]]:
        text = str(raw_text or "").strip()
        if not text:
            return None

        try:
            value = json.loads(text)
            if isinstance(value, dict):
                return value
        except Exception:
            pass

        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            candidate = match.group(0).strip()
            try:
                value = json.loads(candidate)
                if isinstance(value, dict):
                    return value
            except Exception:
                pass

        return None

    def _normalize_plan(self, data: Dict[str, Any], fallback_text: str) -> Dict[str, Any]:
        intent = str(data.get("intent", "respond") or "respond").strip()
        final_answer = str(data.get("final_answer", "") or "").strip()
        raw_steps = data.get("steps", [])

        if not isinstance(raw_steps, list):
            raw_steps = []

        steps: List[Dict[str, Any]] = []
        effective_limit = self._effective_max_steps(raw_steps)
        for item in raw_steps[: effective_limit]:
            normalized = self._normalize_step(item)
            if normalized is not None:
                steps.append(normalized)

        if not steps and not final_answer:
            final_answer = fallback_text

        if intent == "respond" and steps:
            intent = str(steps[0].get("type", "respond") or "respond").strip()

        if intent != "respond" and not steps:
            intent = "respond"

        return self._build_result(
            ok=True,
            intent=intent,
            final_answer=final_answer or "已完成 LLM 規劃",
            steps=steps,
            error=None,
            fallback_used=False,
            reason="llm success",
        )

    def _normalize_step(self, step: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(step, dict):
            return None

        step_type = str(step.get("type", "") or "").strip()
        if not step_type:
            return None

        if step_type == "read_file":
            path = str(step.get("path", "") or "").strip()
            if not path:
                return None
            return {
                "type": "read_file",
                "path": path,
            }

        if step_type == "write_file":
            path = str(step.get("path", "") or "").strip()
            content = str(step.get("content", "") or "")
            use_previous_text = bool(step.get("use_previous_text", False))
            normalized: Dict[str, Any] = {
                "type": "write_file",
                "path": path,
            }
            if content:
                normalized["content"] = content
            if use_previous_text:
                normalized["use_previous_text"] = True
            scope = str(step.get("scope", "") or "").strip()
            if scope:
                normalized["scope"] = scope
            if not path:
                return None
            return normalized

        if step_type == "ensure_file":
            path = str(step.get("path", "") or "").strip()
            if not path:
                return None
            return {
                "type": "ensure_file",
                "path": path,
            }

        if step_type == "web_search":
            query = str(step.get("query", "") or "").strip()
            if not query:
                return None
            return {
                "type": "web_search",
                "query": query,
            }

        if step_type == "command":
            command = str(step.get("command", "") or "").strip()
            if not command:
                return None
            return {
                "type": "command",
                "command": command,
            }

        if step_type in {"llm_generate", "llm"}:
            prompt = str(step.get("prompt", "") or "").strip()
            prompt_template = str(step.get("prompt_template", "") or "").strip()
            mode = str(step.get("mode", "") or "").strip()

            normalized: Dict[str, Any] = {"type": "llm"}
            if prompt:
                normalized["prompt"] = prompt
            if prompt_template:
                normalized["prompt_template"] = prompt_template
            if mode:
                normalized["mode"] = mode

            if not prompt and not prompt_template and not mode:
                return None

            return normalized

        if step_type == "respond":
            message = str(step.get("message", "") or "").strip()
            return {
                "type": "respond",
                "message": message,
            }

        return None

    # ============================================================
    # result
    # ============================================================

    def _build_result(
        self,
        ok: bool,
        intent: str,
        final_answer: str,
        steps: List[Dict[str, Any]],
        error: Optional[str],
        fallback_used: bool,
        reason: str,
    ) -> Dict[str, Any]:
        model_name = ""
        if self.llm_client is not None:
            model_name = str(getattr(self.llm_client, "model", "") or "").strip()

        return {
            "ok": ok,
            "planner_mode": "llm_brain_v4",
            "intent": intent,
            "final_answer": final_answer,
            "steps": steps,
            "error": error,
            "meta": {
                "fallback_used": fallback_used,
                "model": model_name,
                "reason": reason,
                "step_count": len(steps),
            },
        }