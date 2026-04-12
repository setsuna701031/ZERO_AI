from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple


class LLMPlanner:
    """
    LLM Brain / LLM Planner

    修正版目標：
    1. 保留 LLM JSON 規劃能力
    2. 在進 LLM 前，先走 deterministic guard，避免明確檔案操作被 LLM 誤判
    3. 支援 ensure_file，避免「建立但沒內容」被轉成 write_file(path, "")
    4. 支援多子句：例如「幫我建立一個 a.txt，然後再讀出來」
    5. 支援跨子句 last_path 記憶
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

        # 先走 deterministic guard，明確可判斷的檔案/命令需求不要交給 LLM 自由發揮
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
        clauses = self._split_clauses(text)
        if not clauses:
            return None

        steps: List[Dict[str, Any]] = []
        last_path: Optional[str] = None

        for clause in clauses:
            clause_steps, last_path = self._plan_single_clause(clause, last_path=last_path)
            if clause_steps is None:
                # 只要有任一子句判不準，就整句交回 LLM，避免 deterministic 誤傷一般聊天
                return None
            steps.extend(clause_steps)

        if not steps:
            return None

        intent = str(steps[0].get("type", "respond") or "respond").strip()

        return self._build_result(
            ok=True,
            intent=intent,
            final_answer=f"已規劃 {len(steps)} 個步驟",
            steps=steps[: self.max_steps],
            error=None,
            fallback_used=False,
            reason="deterministic guard matched",
        )

    def _plan_single_clause(
        self,
        text: str,
        last_path: Optional[str] = None,
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        stripped = str(text or "").strip()
        if not stripped:
            return [], last_path

        # 1. command
        command = self._extract_command(stripped)
        if command:
            return [{"type": "command", "command": command}], last_path

        # 2. write / ensure_file
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

        # 3. read
        if self._looks_like_read(stripped):
            read_path = self._resolve_read_path(stripped, last_path=last_path)
            if not read_path:
                return None, last_path
            return [{"type": "read_file", "path": read_path}], read_path

        # 4. search
        if self._looks_like_search(stripped):
            return [{"type": "web_search", "query": stripped}], last_path

        # 5. 明確回覆型句子，可直接 respond
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
        for item in raw_steps[: self.max_steps]:
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
            if not path:
                return None
            return {
                "type": "write_file",
                "path": path,
                "content": content,
            }

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

        if step_type == "llm_generate":
            prompt = str(step.get("prompt", "") or "").strip()
            if not prompt:
                return None
            return {
                "type": "llm_generate",
                "prompt": prompt,
            }

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
            "planner_mode": "llm_brain_v1",
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