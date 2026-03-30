from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


class Planner:
    """
    最小可用 deterministic planner v1

    目標：
    1. 將常見中文 / 英文任務轉成 steps
    2. 對齊 ZERO 現在的 step 格式
    3. 先打通 planner -> executor -> tool 鏈路
    4. 看不懂時回傳 respond，不亂寫檔
    """

    def __init__(
        self,
        memory_store: Any = None,
        runtime_store: Any = None,
        step_executor: Any = None,
        workspace_dir: str = "workspace",
        workspace_root: Optional[str] = None,
        debug: bool = False,
    ) -> None:
        self.memory_store = memory_store
        self.runtime_store = runtime_store
        self.step_executor = step_executor
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
                "final_answer": "空白輸入，無法規劃。",
                "steps": [
                    {
                        "type": "respond",
                        "message": "空白輸入，無法規劃。",
                    }
                ],
            }

        steps = self._plan_steps(text=text, context=context, route=route)

        if not steps:
            fallback = f"已收到：{text}"
            return {
                "planner_mode": "deterministic_fallback_respond",
                "intent": "respond",
                "final_answer": fallback,
                "steps": [
                    {
                        "type": "respond",
                        "message": fallback,
                    }
                ],
            }

        return {
            "planner_mode": "deterministic_v1",
            "intent": self._infer_intent(text),
            "final_answer": self._summarize_plan(text, steps),
            "steps": steps,
        }

    # 向下相容
    def build_plan(
        self,
        goal: str = "",
        task_dir: str = "",
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        context = {
            "user_input": goal,
            "workspace": task_dir or self.workspace_dir,
        }
        result = self.plan(context=context, user_input=goal)
        steps = result.get("steps", [])
        if isinstance(steps, list):
            return steps
        return []

    def run(
        self,
        context: Optional[Dict[str, Any]] = None,
        user_input: str = "",
        route: Any = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return self.plan(context=context, user_input=user_input, route=route, **kwargs)

    # ============================================================
    # main planning logic
    # ============================================================

    def _plan_steps(
        self,
        text: str,
        context: Dict[str, Any],
        route: Any = None,
    ) -> List[Dict[str, Any]]:
        normalized_text = self._normalize_text(text)
        clauses = self._split_clauses(normalized_text)

        all_steps: List[Dict[str, Any]] = []

        for clause in clauses:
            clause = clause.strip()
            if not clause:
                continue

            clause_steps = self._plan_clause(clause=clause, context=context, route=route)
            if clause_steps:
                all_steps.extend(clause_steps)

        if all_steps:
            return all_steps

        # 如果整句拆不出，就直接拿原句判一次
        return self._plan_clause(clause=normalized_text, context=context, route=route)

    def _plan_clause(
        self,
        clause: str,
        context: Dict[str, Any],
        route: Any = None,
    ) -> List[Dict[str, Any]]:
        workspace_tool = self._pick_tool(
            ["workspace", "workspace_tool", "write_file", "workspace_write", "file_write"]
        )
        search_tool = self._pick_tool(
            ["web_search", "search_web", "search", "websearch"]
        )
        command_tool = self._pick_tool(
            ["command", "command_tool"]
        )

        # --------------------------------------------------------
        # read file
        # --------------------------------------------------------
        read_path = self._extract_read_path(clause)
        if read_path and workspace_tool:
            return [
                {
                    "type": "tool",
                    "tool_name": workspace_tool,
                    "tool_input": {
                        "action": "read",
                        "path": read_path,
                    },
                }
            ]

        # --------------------------------------------------------
        # mkdir / create folder
        # --------------------------------------------------------
        mkdir_path = self._extract_mkdir_path(clause)
        if mkdir_path and workspace_tool:
            return [
                {
                    "type": "tool",
                    "tool_name": workspace_tool,
                    "tool_input": {
                        "action": "mkdir",
                        "path": mkdir_path,
                    },
                }
            ]

        # --------------------------------------------------------
        # append file
        # --------------------------------------------------------
        append_info = self._extract_append_request(clause)
        if append_info and workspace_tool:
            return [
                {
                    "type": "tool",
                    "tool_name": workspace_tool,
                    "tool_input": {
                        "action": "append",
                        "path": append_info["path"],
                        "content": append_info["content"],
                    },
                }
            ]

        # --------------------------------------------------------
        # write file
        # --------------------------------------------------------
        write_info = self._extract_write_request(clause, context=context)
        if write_info and workspace_tool:
            steps: List[Dict[str, Any]] = []

            parent_dir = self._parent_dir(write_info["path"])
            if parent_dir:
                steps.append(
                    {
                        "type": "tool",
                        "tool_name": workspace_tool,
                        "tool_input": {
                            "action": "mkdir",
                            "path": parent_dir,
                        },
                    }
                )

            steps.append(
                {
                    "type": "tool",
                    "tool_name": workspace_tool,
                    "tool_input": {
                        "action": "write",
                        "path": write_info["path"],
                        "content": write_info["content"],
                    },
                }
            )
            return steps

        # --------------------------------------------------------
        # search
        # --------------------------------------------------------
        if self._looks_like_search_query(clause) and search_tool:
            return [
                {
                    "type": "tool",
                    "tool_name": search_tool,
                    "tool_input": {
                        "query": clause,
                    },
                }
            ]

        # --------------------------------------------------------
        # command
        # --------------------------------------------------------
        command_text = self._extract_command_text(clause)
        if command_text and command_tool:
            return [
                {
                    "type": "tool",
                    "tool_name": command_tool,
                    "tool_input": {
                        "command": command_text,
                    },
                }
            ]

        # --------------------------------------------------------
        # plan / breakdown request
        # --------------------------------------------------------
        if self._looks_like_plan_request(clause):
            return [
                {
                    "type": "respond",
                    "message": self._make_breakdown(clause),
                }
            ]

        return []

    # ============================================================
    # clause split
    # ============================================================

    def _normalize_text(self, text: str) -> str:
        text = str(text or "").strip()
        text = text.replace("，", ",")
        text = text.replace("。", ".")
        text = text.replace("；", ";")
        text = text.replace("：", ":")
        return text

    def _split_clauses(self, text: str) -> List[str]:
        if not text:
            return []

        tmp = text
        connectors = [
            "然後",
            "接著",
            "並且",
            "並",
            "再",
            "之後",
            "and then",
            " then ",
        ]

        for token in connectors:
            tmp = tmp.replace(token, "|")

        tmp = tmp.replace(",", "|")
        tmp = tmp.replace(";", "|")

        parts = [p.strip() for p in tmp.split("|")]
        return [p for p in parts if p]

    # ============================================================
    # read parsing
    # ============================================================

    def _extract_read_path(self, text: str) -> Optional[str]:
        lowered = text.lower()

        if not any(k in lowered or k in text for k in ["讀取", "查看", "打開", "read", "open", "show"]):
            return None

        path = self._extract_file_path(text)
        return path

    # ============================================================
    # mkdir parsing
    # ============================================================

    def _extract_mkdir_path(self, text: str) -> Optional[str]:
        lowered = text.lower()

        mkdir_keywords = [
            "建立資料夾",
            "建立文件夾",
            "新增資料夾",
            "創建資料夾",
            "create folder",
            "make folder",
            "mkdir",
        ]

        if not any(k in text or k in lowered for k in mkdir_keywords):
            return None

        patterns = [
            r"(?:建立資料夾|建立文件夾|新增資料夾|創建資料夾)\s+([^\s]+)",
            r"(?:create folder|make folder|mkdir)\s+([^\s]+)",
        ]

        for pattern in patterns:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if m:
                return self._strip_quotes(m.group(1))

        return None

    # ============================================================
    # write parsing
    # ============================================================

    def _extract_write_request(
        self,
        text: str,
        context: Dict[str, Any],
    ) -> Optional[Dict[str, str]]:
        lowered = text.lower()

        write_keywords = [
            "寫入",
            "建立檔案",
            "新增檔案",
            "創建檔案",
            "存成",
            "存檔",
            "寫檔",
            "create file",
            "write file",
            "save file",
        ]

        if not any(k in text or k in lowered for k in write_keywords) and not self._contains_filename(text):
            return None

        path = self._extract_file_path(text)
        content = self._extract_write_content(text)

        # 僅有檔名但沒明確寫入關鍵字，且像「讀取 a.txt」這類句子，不要誤判
        if path and self._looks_like_read_request(text):
            return None

        # 特例：像「在 test 裡面建立 a.txt」這種只有 path 沒 content
        if path and content is None:
            content = ""

        if not path:
            inferred = self._infer_output_path(text=text, context=context)
            if inferred:
                path = inferred

        if not path:
            return None

        if content is None:
            content = text

        return {
            "path": path,
            "content": content,
        }

    def _extract_append_request(self, text: str) -> Optional[Dict[str, str]]:
        lowered = text.lower()

        append_keywords = [
            "追加",
            "附加",
            "append",
        ]

        if not any(k in text or k in lowered for k in append_keywords):
            return None

        path = self._extract_file_path(text)
        if not path:
            return None

        content = self._extract_write_content(text)
        if content is None:
            content = text

        return {
            "path": path,
            "content": content,
        }

    def _extract_write_content(self, text: str) -> Optional[str]:
        patterns = [
            r"內容是\s+(.+)$",
            r"內容為\s+(.+)$",
            r"寫入\s+(.+?)\s+到\s+[^\s]+$",
            r"寫入\s+(.+?)\s+進\s+[^\s]+$",
            r"寫入\s+(.+)$",
            r"content is\s+(.+)$",
            r"content:\s*(.+)$",
        ]

        for pattern in patterns:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if m:
                return self._strip_quotes(m.group(1).strip())

        # 引號內容
        quote_patterns = [
            r'"([^"]+)"',
            r"'([^']+)'",
        ]
        for pattern in quote_patterns:
            m = re.search(pattern, text)
            if m:
                return m.group(1)

        return None

    # ============================================================
    # file path parsing
    # ============================================================

    def _extract_file_path(self, text: str) -> Optional[str]:
        patterns = [
            r'([A-Za-z0-9_\-./\\]+?\.(?:py|txt|md|json|yaml|yml|csv|log))',
        ]

        for pattern in patterns:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if m:
                return self._normalize_path(m.group(1))

        # 中文語境：在 test 裡面建立 a.txt
        inside_match = re.search(
            r"在\s+([A-Za-z0-9_\-./\\]+)\s+裡面.*?([A-Za-z0-9_\-./\\]+?\.(?:py|txt|md|json|yaml|yml|csv|log))",
            text,
            flags=re.IGNORECASE,
        )
        if inside_match:
            folder = self._normalize_path(inside_match.group(1))
            filename = self._normalize_path(inside_match.group(2))
            filename = filename.split("/")[-1]
            return f"{folder}/{filename}"

        return None

    def _infer_output_path(self, text: str, context: Dict[str, Any]) -> Optional[str]:
        # 有明確副檔名時才推
        if self._contains_filename(text):
            path = self._extract_file_path(text)
            if path:
                return path

        # 像「建立 hello.txt」這種通常上面會抓到，不再硬推 output.txt
        return None

    def _contains_filename(self, text: str) -> bool:
        return bool(
            re.search(r'[A-Za-z0-9_\-./\\]+?\.(?:py|txt|md|json|yaml|yml|csv|log)', text, flags=re.IGNORECASE)
        )

    def _normalize_path(self, path: str) -> str:
        value = self._strip_quotes(path).strip()
        value = value.replace("\\", "/")
        value = re.sub(r"/+", "/", value)

        # 防止 fallback 再塞出 workspace/workspace
        if value.startswith("./"):
            value = value[2:]

        if value.lower().startswith("workspace/"):
            value = value[len("workspace/"):]

        return value

    def _parent_dir(self, path: str) -> str:
        normalized = self._normalize_path(path)
        if "/" not in normalized:
            return ""
        return normalized.rsplit("/", 1)[0]

    def _strip_quotes(self, value: str) -> str:
        value = str(value or "").strip()
        if len(value) >= 2:
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                return value[1:-1]
        return value

    # ============================================================
    # intent heuristics
    # ============================================================

    def _infer_intent(self, text: str) -> str:
        lowered = text.lower()

        if self._looks_like_read_request(text):
            return "read_file"
        if self._extract_mkdir_path(text):
            return "mkdir"
        if self._extract_append_request(text):
            return "append_file"
        if self._extract_write_request(text, context={}):
            return "write_file"
        if self._looks_like_search_query(text):
            return "web_search"
        if self._extract_command_text(text):
            return "command"
        if self._looks_like_plan_request(text):
            return "planning"
        return "respond"

    def _looks_like_read_request(self, text: str) -> bool:
        lowered = text.lower()
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

    def _looks_like_search_query(self, text: str) -> bool:
        lowered = text.lower()
        keywords = [
            "查",
            "搜尋",
            "搜索",
            "規格",
            "資料",
            "教學",
            "怎麼設定",
            "怎麼安裝",
            "怎麼用",
            "是什麼",
            "多少",
            "版本",
            "說明",
            "web",
            "search",
            "spec",
            "specs",
            "lookup",
        ]
        return any(k in text or k in lowered for k in keywords)

    def _looks_like_plan_request(self, text: str) -> bool:
        lowered = text.lower()
        keywords = [
            "規劃",
            "計畫",
            "拆解",
            "步驟",
            "怎麼做",
            "如何做",
            "roadmap",
            "plan",
            "breakdown",
            "steps",
        ]
        return any(k in text or k in lowered for k in keywords)

    def _extract_command_text(self, text: str) -> str:
        stripped = text.strip()

        prefixes = [
            "執行 ",
            "執行:",
            "執行：",
            "run ",
            "cmd ",
            "command ",
        ]

        lowered = stripped.lower()
        for prefix in prefixes:
            if lowered.startswith(prefix.lower()):
                return stripped[len(prefix):].strip()

        return ""

    # ============================================================
    # tool helpers
    # ============================================================

    def _pick_tool(self, candidates: List[str]) -> Optional[str]:
        actual_tools = self._list_tools()
        if not actual_tools:
            return None

        def norm(x: Any) -> str:
            return str(x).strip().lower().replace("-", "_").replace(" ", "_")

        normalized_actual = {norm(t): t for t in actual_tools}

        alias_map = {
            "web_search": ["search_web", "search", "websearch"],
            "search_web": ["web_search", "search", "websearch"],
            "search": ["web_search", "search_web", "websearch"],
            "websearch": ["web_search", "search_web", "search"],
            "workspace": ["workspace_tool", "write_file", "workspace_write", "file_write"],
            "workspace_tool": ["workspace", "write_file", "workspace_write", "file_write"],
            "write_file": ["workspace", "workspace_tool", "workspace_write", "file_write"],
            "workspace_write": ["workspace", "workspace_tool", "write_file", "file_write"],
            "file_write": ["workspace", "workspace_tool", "write_file", "workspace_write"],
            "command": ["command_tool"],
            "command_tool": ["command"],
        }

        for candidate in candidates:
            nc = norm(candidate)

            if nc in normalized_actual:
                return normalized_actual[nc]

            for alias in alias_map.get(nc, []):
                na = norm(alias)
                if na in normalized_actual:
                    return normalized_actual[na]

        return None

    def _list_tools(self) -> List[str]:
        registry = self._get_tool_registry()
        if registry is None:
            return []

        list_tools_fn = getattr(registry, "list_tools", None)
        if callable(list_tools_fn):
            try:
                result = list_tools_fn()
                if isinstance(result, dict):
                    if isinstance(result.get("tools"), list):
                        return [str(x) for x in result.get("tools", [])]
                    if isinstance(result.get("items"), list):
                        names: List[str] = []
                        for item in result.get("items", []):
                            if isinstance(item, dict):
                                name = item.get("name") or item.get("tool_name")
                                if name:
                                    names.append(str(name))
                            else:
                                names.append(str(item))
                        return names
                if isinstance(result, list):
                    names = []
                    for item in result:
                        if isinstance(item, dict):
                            name = item.get("name") or item.get("tool_name")
                            if name:
                                names.append(str(name))
                        else:
                            names.append(str(item))
                    return names
            except Exception:
                pass

        for attr_name in ("tools", "_tools", "registry"):
            value = getattr(registry, attr_name, None)
            if isinstance(value, dict):
                return [str(k) for k in value.keys()]

        return []

    def _get_tool_registry(self) -> Optional[Any]:
        if self.step_executor is not None:
            registry = getattr(self.step_executor, "tool_registry", None)
            if registry is not None:
                return registry
        return None

    # ============================================================
    # response helpers
    # ============================================================

    def _make_breakdown(self, text: str) -> str:
        return (
            "可將任務拆解為：\n"
            "1. 需求分析\n"
            "2. 設計解法\n"
            "3. 實作\n"
            "4. 測試\n"
            "5. 修正與優化\n\n"
            f"任務：{text}"
        )

    def _summarize_plan(self, text: str, steps: List[Dict[str, Any]]) -> str:
        if not steps:
            return f"已收到：{text}"

        if len(steps) == 1:
            step = steps[0]
            step_type = str(step.get("type") or "")
            if step_type == "tool":
                tool_name = step.get("tool_name", "")
                return f"已規劃 1 個步驟，使用工具：{tool_name}"
            return "已規劃 1 個步驟。"

        return f"已規劃 {len(steps)} 個步驟。"