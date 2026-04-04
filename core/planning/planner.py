from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


class Planner:
    """
    Deterministic Planner v10

    重點：
    1. 保留 Windows shell 指令，例如：cmd /c echo hello
    2. 只把 cmd: xxx / run: xxx / command: xxx 視為前綴式命令語法
    3. 若 router 已經判定 mode=command，planner 直接保留原字串，不再二次剝前綴
    4. 支援 multi-step planning
    5. 支援 command / read / write / search 混合拆步
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
    ) -> None:
        self.memory_store = memory_store
        self.runtime_store = runtime_store
        self.step_executor = step_executor
        self.tool_registry = tool_registry
        self.workspace_dir = workspace_root or workspace_dir or "workspace"
        self.debug = debug

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
                "planner_mode": "deterministic_v10",
                "intent": "respond",
                "final_answer": "空白輸入",
                "steps": [],
            }

        steps = self._plan_steps(text=text, route=route)

        return {
            "planner_mode": "deterministic_v10",
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
        result = self.plan(
            context={"user_input": goal, "workspace": task_dir or self.workspace_dir},
            user_input=goal,
            route=route,
        )
        steps = result.get("steps", [])
        if isinstance(steps, list):
            return steps
        return []

    def build_plan_for_goal(
        self,
        goal: str = "",
        task_dir: str = "",
        route: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        return self.build_plan(goal=goal, task_dir=task_dir, route=route, **kwargs)

    # ============================================================
    # multi step planner
    # ============================================================

    def _plan_steps(self, text: str, route: Any = None) -> List[Dict[str, Any]]:
        stripped = str(text or "").strip()

        # router 已明確判斷 command 時，不拆 clause，避免 shell 指令被拆壞
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

        # router 已經判定 command，直接整段保留
        if self._is_command_route(route):
            return [
                {
                    "type": "command",
                    "command": stripped,
                }
            ]

        # command 優先
        cmd = self._extract_command(stripped)
        if cmd:
            return [
                {
                    "type": "command",
                    "command": cmd,
                }
            ]

        # read
        read_path = self._extract_read_path(stripped)
        if read_path:
            return [
                {
                    "type": "read_file",
                    "path": read_path,
                }
            ]

        # write
        write = self._extract_write_request(stripped)
        if write:
            return [
                {
                    "type": "write_file",
                    "path": write["path"],
                    "content": write["content"],
                }
            ]

        # search
        if self._looks_like_search(stripped):
            return [
                {
                    "type": "web_search",
                    "query": stripped,
                }
            ]

        # fallback：如果看起來像一般命令句但沒前綴，不自動轉 command
        return []

    # ============================================================
    # split clauses
    # ============================================================

    def _split_clauses(self, text: str) -> List[str]:
        tmp = str(text or "").strip()
        if not tmp:
            return []

        # 先保護引號內容，避免把 content: "a,b;c" 這種拆壞
        protected_text, placeholders = self._protect_quoted_segments(tmp)

        connectors = [
            "然後",
            "接著",
            "之後",
            "再",
            "並且",
            "以及",
            "and then",
            " then ",
        ]

        for c in connectors:
            protected_text = protected_text.replace(c, "|")

        protected_text = protected_text.replace("；", "|")
        protected_text = protected_text.replace(";", "|")
        protected_text = protected_text.replace("，", "|")
        protected_text = protected_text.replace(",", "|")

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

        # 故意不支援 ^cmd\s+(.+)$
        # 避免把 Windows 的 `cmd /c xxx` 誤當成前綴語法
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

        # 直接輸入 python / py 也視為 command
        if lowered.startswith("python "):
            return stripped

        if lowered.startswith("py "):
            return stripped

        return None

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
            content = self._generate_content_from_filename(path)

        return {
            "path": path,
            "content": content,
        }

    def _generate_content_from_filename(self, path: str) -> str:
        normalized = path.replace("\\", "/").lower()

        if normalized.endswith(".py"):
            return "print('hello')\n"

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