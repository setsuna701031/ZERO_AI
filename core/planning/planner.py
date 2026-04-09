from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional


class Planner:
    """
    Deterministic Planner v12

    重點：
    1. 支援多步驟 clause split
    2. command / read / write / search 混合拆步
    3. planner 階段直接補 step metadata
    4. 內建 demo pipeline 任務，方便測 scheduler / recovery
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
        memory_store: Any = None,
        runtime_store: Any = None,
        step_executor: Any = None,
        tool_registry: Any = None,
        workspace_dir: str = "workspace",
        workspace_root: Optional[str] = None,
        debug: bool = False,
    ) -> None:
        self.memory_store = memory_store
        self.runtime_store = runtime_store
        self.step_executor = step_executor
        self.tool_registry = tool_registry
        self.workspace_dir = workspace_root or workspace_dir or "workspace"
        self.debug = debug

        print("### USING NEW PLANNER ###")

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
            return {
                "planner_mode": "deterministic_v12",
                "intent": "respond",
                "final_answer": "空白輸入",
                "steps": [],
            }

        raw_steps = self._plan_steps(text=text, route=route)
        task_name = self._infer_task_name(task_dir=str(context.get("workspace", "") or ""), goal=text)
        steps = self._apply_step_metadata(raw_steps, task_name=task_name)

        return {
            "planner_mode": "deterministic_v12",
            "intent": self._infer_intent(text=text, route=route, steps=steps),
            "final_answer": f"已規劃 {len(steps)} 個步驟",
            "steps": steps,
        }

    def run(
        self,
        context: Optional[Dict[str, Any]] = None,
        user_input: str = "",
        route: Any = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return self.plan(context=context, user_input=user_input, route=route, **kwargs)

    def build_plan(
        self,
        goal: str = "",
        task_dir: str = "",
        route: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        raw_steps = self._plan_steps(text=goal, route=route)
        task_name = self._infer_task_name(task_dir=task_dir, goal=goal)
        return self._apply_step_metadata(raw_steps, task_name=task_name)

    def build_plan_for_goal(
        self,
        goal: str = "",
        task_dir: str = "",
        route: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        return self.build_plan(goal=goal, task_dir=task_dir, route=route, **kwargs)

    # ============================================================
    # demo tasks
    # ============================================================

    def _build_demo_pipeline_steps(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "write_file",
                "path": "a.txt",
                "content": "A",
                "produces_files": ["a.txt"],
            },
            {
                "type": "write_file",
                "path": "b.txt",
                "content": "B",
                "produces_files": ["b.txt"],
            },
            {
                "type": "write_file",
                "path": "c.txt",
                "content": "C",
                "produces_files": ["c.txt"],
            },
            {
                "type": "read_file",
                "path": "a.txt",
                "consumes_files": ["a.txt"],
            },
            {
                "type": "read_file",
                "path": "b.txt",
                "consumes_files": ["b.txt"],
            },
            {
                "type": "read_file",
                "path": "c.txt",
                "consumes_files": ["c.txt"],
            },
        ]

    def _is_demo_pipeline_request(self, text: str) -> bool:
        lowered = str(text or "").strip().lower()
        candidates = {
            "demo pipeline",
            "demo_pipeline",
            "pipeline demo",
            "測試 pipeline",
            "demo 任務",
            "demo task",
        }
        return any(token in lowered for token in candidates)

    # ============================================================
    # multi step planner
    # ============================================================

    def _plan_steps(self, text: str, route: Any = None) -> List[Dict[str, Any]]:
        stripped = str(text or "").strip()
        if not stripped:
            return []

        if self._is_demo_pipeline_request(stripped):
            return self._build_demo_pipeline_steps()

        if self._is_command_route(route):
            return [
                {
                    "type": "command",
                    "command": stripped,
                }
            ]

        clauses = self._split_clauses(stripped)
        steps: List[Dict[str, Any]] = []

        for clause in clauses:
            clause = clause.strip()
            if not clause:
                continue

            clause_steps = self._plan_single_clause(clause, route=route)
            if clause_steps:
                steps.extend(clause_steps)

        return steps

    # ============================================================
    # clause planner
    # ============================================================

    def _plan_single_clause(self, text: str, route: Any = None) -> List[Dict[str, Any]]:
        stripped = str(text or "").strip()
        if not stripped:
            return []

        stripped = self._strip_clause_prefix(stripped)

        if not stripped:
            return []

        if self._is_command_route(route):
            return [
                {
                    "type": "command",
                    "command": stripped,
                }
            ]

        cmd = self._extract_command(stripped)
        if cmd:
            return [
                {
                    "type": "command",
                    "command": cmd,
                }
            ]

        read_path = self._extract_read_path(stripped)
        if read_path:
            return [
                {
                    "type": "read_file",
                    "path": read_path,
                    "consumes_files": [read_path],
                }
            ]

        write = self._extract_write_request(stripped)
        if write:
            return [
                {
                    "type": "write_file",
                    "path": write["path"],
                    "content": write["content"],
                    "produces_files": [write["path"]],
                }
            ]

        if self._looks_like_search(stripped):
            return [
                {
                    "type": "web_search",
                    "query": stripped,
                }
            ]

        return []

    def _strip_clause_prefix(self, text: str) -> str:
        stripped = str(text or "").strip()

        prefixes = [
            "先",
            "再",
            "然後",
            "接著",
            "之後",
            "請",
            "幫我",
            "先幫我",
            "再幫我",
            "先去",
            "再去",
        ]

        changed = True
        while changed:
            changed = False
            for prefix in prefixes:
                if stripped.startswith(prefix):
                    stripped = stripped[len(prefix):].strip()
                    changed = True

        return stripped

    # ============================================================
    # step metadata
    # ============================================================

    def _apply_step_metadata(
        self,
        steps: List[Dict[str, Any]],
        task_name: str = "",
    ) -> List[Dict[str, Any]]:
        normalized_steps: List[Dict[str, Any]] = []
        total = len(steps)

        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue

            normalized = self._normalize_step_metadata(
                step=step,
                step_index=index,
                step_count=total,
                task_name=task_name,
            )
            normalized_steps.append(normalized)

        return normalized_steps

    def _normalize_step_metadata(
        self,
        step: Dict[str, Any],
        step_index: int,
        step_count: int,
        task_name: str,
    ) -> Dict[str, Any]:
        normalized = dict(step or {})
        step_type = str(normalized.get("type", "") or "").strip().lower()

        if not step_type:
            step_type = "unknown"
            normalized["type"] = step_type

        normalized["step_index"] = step_index
        normalized["step_count"] = step_count

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
                step_index=step_index,
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

        if step_type in {"command", "shell", "execute"}:
            command = str(step.get("command", "") or "").strip()
            tokens = self._extract_file_references_from_command(command)
            return tokens

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
        safe_step = dict(step or {})
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

    def _infer_task_name(self, task_dir: str, goal: str) -> str:
        task_dir = str(task_dir or "").strip()
        if task_dir:
            task_dir = task_dir.replace("\\", "/").rstrip("/")
            if "/" in task_dir:
                return task_dir.split("/")[-1]
            return task_dir

        text = str(goal or "").strip()
        if not text:
            return "task"

        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
        return f"task_{digest}"

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

    # ============================================================
    # split clauses
    # ============================================================

    def _split_clauses(self, text: str) -> List[str]:
        tmp = str(text or "").strip()
        if not tmp:
            return []

        protected_text, placeholders = self._protect_quoted_segments(tmp)

        connectors = [
            "然後",
            "接著",
            "之後",
            "並且",
            "以及",
            "and then",
        ]

        for c in connectors:
            protected_text = protected_text.replace(c, "|")

        protected_text = protected_text.replace("；", "|")
        protected_text = protected_text.replace(";", "|")

        parts = [self._restore_quoted_segments(p.strip(), placeholders) for p in protected_text.split("|")]
        return [p for p in parts if p.strip()]

    def _protect_quoted_segments(self, text: str) -> tuple[str, Dict[str, str]]:
        placeholders: Dict[str, str] = {}

        def repl(match: re.Match[str]) -> str:
            key = f"__QUOTE_{len(placeholders)}__"
            placeholders[key] = match.group(0)
            return key

        protected = re.sub(r'"[^"]*"|\'[^\']*\'', repl, text)
        return protected, placeholders

    def _restore_quoted_segments(self, text: str, placeholders: Dict[str, str]) -> str:
        restored = text
        for key, value in placeholders.items():
            restored = restored.replace(key, value)
        return restored

    # ============================================================
    # command
    # ============================================================

    def _extract_command(self, text: str) -> Optional[str]:
        stripped = str(text or "").strip()
        lowered = stripped.lower()

        patterns = [
            r"^cmd\s*:\s*(.+)$",
            r"^run\s*:\s*(.+)$",
            r"^run\s+(.+)$",
            r"^command\s*:\s*(.+)$",
            r"^command\s+(.+)$",
            r"^execute\s+(.+)$",
            r"^shell\s+(.+)$",
            r"^bash\s+(.+)$",
            r"^執行\s+(.+)$",
        ]

        for p in patterns:
            m = re.match(p, stripped, flags=re.IGNORECASE)
            if m:
                return m.group(1).strip()

        if lowered.startswith("python "):
            return stripped

        if lowered.startswith("py "):
            return stripped

        if lowered.startswith("cmd /c "):
            return stripped

        if lowered.startswith("powershell "):
            return stripped

        return None

    def _extract_file_references_from_command(self, command: str) -> List[str]:
        if not command:
            return []

        matches = re.findall(
            r'([A-Za-z0-9_\-./\\]+?\.(?:py|txt|md|json|yaml|yml|csv|log))',
            command,
            flags=re.IGNORECASE,
        )
        result: List[str] = []
        for item in matches:
            text = str(item).replace("\\", "/").strip()
            if text:
                result.append(text)
        return result

    def _is_command_route(self, route: Any) -> bool:
        if not isinstance(route, dict):
            return False

        mode = str(route.get("mode", "")).strip().lower()
        tool_name = str(route.get("tool_name", "")).strip().lower()

        if mode == "command":
            return True

        if tool_name == "command":
            return True

        return False

    # ============================================================
    # read
    # ============================================================

    def _extract_read_path(self, text: str) -> Optional[str]:
        if self._looks_like_read(text):
            return self._extract_file_path(text)
        return None

    def _looks_like_read(self, text: str) -> bool:
        lowered = str(text or "").lower()
        keywords = [
            "讀取",
            "查看",
            "打開",
            "顯示",
            "read",
            "open",
            "show",
            "cat ",
        ]
        return any(k in text or k in lowered for k in keywords)

    # ============================================================
    # write file
    # ============================================================

    def _extract_write_request(self, text: str) -> Optional[Dict[str, str]]:
        lowered = str(text or "").lower()

        if self._extract_command(text):
            return None

        if self._looks_like_read(text):
            return None

        write_keywords = [
            "建立",
            "新增",
            "寫",
            "寫入",
            "create",
            "write",
            "save",
        ]

        has_write_keyword = any(k in text or k in lowered for k in write_keywords)
        has_filename = self._contains_filename(text)

        if not has_filename:
            return None

        if not has_write_keyword and not self._looks_like_filename_only_request(text):
            return None

        path = self._extract_file_path(text)
        if not path:
            return None

        content = self._extract_write_content(text)
        if content is None:
            content = self._generate_content_from_filename(path, text)

        return {
            "path": path,
            "content": content,
        }

    def _generate_content_from_filename(self, path: str, goal: str) -> str:
        normalized = path.replace("\\", "/").lower()

        if normalized.endswith(".py"):
            if "hello" in goal.lower():
                return 'print("hello world")\n'
            return "# generated by ZERO\n"

        if normalized.endswith(".md"):
            return "# Document\n"

        if normalized.endswith(".json"):
            return "{}\n"

        if normalized.endswith(".csv"):
            return "column1,column2\n"

        return ""

    def _extract_write_content(self, text: str) -> Optional[str]:
        patterns = [
            r"內容是\s+(.+)$",
            r"內容為\s+(.+)$",
            r"內容:\s*(.+)$",
            r"content is\s+(.+)$",
            r"content:\s*(.+)$",
        ]

        for p in patterns:
            m = re.search(p, text, flags=re.IGNORECASE)
            if m:
                return m.group(1).strip()

        return None

    # ============================================================
    # search
    # ============================================================

    def _looks_like_search(self, text: str) -> bool:
        lowered = str(text or "").lower()
        keywords = ["搜尋", "search", "查", "規格", "是什麼"]
        return any(k in text or k in lowered for k in keywords)

    # ============================================================
    # file path
    # ============================================================

    def _extract_file_path(self, text: str) -> Optional[str]:
        m = re.search(
            r'([A-Za-z0-9_\-./\\]+?\.(?:py|txt|md|json|yaml|yml|csv|log))',
            text,
            flags=re.IGNORECASE,
        )
        if m:
            return m.group(1).replace("\\", "/")
        return None

    def _contains_filename(self, text: str) -> bool:
        return bool(
            re.search(
                r'([A-Za-z0-9_\-./\\]+?\.(?:py|txt|md|json|yaml|yml|csv|log))',
                text,
                flags=re.IGNORECASE,
            )
        )

    def _looks_like_filename_only_request(self, text: str) -> bool:
        lowered = str(text or "").lower()
        return any(k in text or k in lowered for k in ["建立", "新增", "create", "write", "save"])

    # ============================================================
    # intent
    # ============================================================

    def _infer_intent(self, text: str, route: Any = None, steps: Optional[List[Dict[str, Any]]] = None) -> str:
        if self._is_command_route(route):
            return "command"

        if self._extract_command(text):
            return "command"

        if steps:
            first_type = str(steps[0].get("type", "")).strip().lower()
            if first_type:
                return first_type

        if self._looks_like_read(text):
            return "read_file"

        if self._extract_write_request(text):
            return "write_file"

        if self._looks_like_search(text):
            return "web_search"

        return "respond"