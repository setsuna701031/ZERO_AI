from __future__ import annotations

from typing import Any

from core.agent_loop import AgentLoop
from core.project_agent import ProjectAgent


class Executor:
    def __init__(
        self,
        tool_registry,
        llm_client,
        memory_manager,
        response_builder,
        session_state,
    ) -> None:
        self.tool_registry = tool_registry
        self.llm_client = llm_client
        self.memory_manager = memory_manager
        self.response_builder = response_builder
        self.session_state = session_state

        self.agent_loop = AgentLoop(
            tool_registry=tool_registry,
            llm_client=llm_client,
        )
        self.project_agent = ProjectAgent(
            llm_client=llm_client,
            executor=self,
        )

    def execute(self, route: dict[str, Any] | str) -> str:
        # 讓 ProjectAgent / TaskRunner 可以直接丟字串步驟進來
        if isinstance(route, str):
            route = self.session_state.last_route = None or {"_raw_text": route}
            route = self._route_text(route["_raw_text"])

        self.session_state.last_route = route

        route_type = route.get("route_type")
        action = route.get("action")
        args = route.get("args", {})
        text = route.get("original_text", "")

        if route_type == "empty":
            return "請輸入內容。"

        if route_type == "system":
            if action == "help":
                return self._help_text()
            if action == "exit":
                return "__EXIT__"

        if route_type == "memory":
            if action == "show":
                result = self.memory_manager.show_memory()
                return self.response_builder.build_memory_result(result)

            if action == "remember":
                remember_text = args.get("text", "")
                result = self.memory_manager.remember(remember_text)
                return self.response_builder.build_memory_result(result)

        if route_type == "tool":
            tool = self.tool_registry.get(action)
            if tool is None:
                return self.response_builder.build_error(f"找不到工具: {action}")

            result = tool.run(args)
            self.session_state.add_recent_tool(action)

            path = args.get("path")
            if path:
                self.session_state.add_recent_file(path)

            return self.response_builder.build_tool_result(action, result)

        if route_type == "explain":
            read_tool = self.tool_registry.get("read_file")
            if read_tool is None:
                return self.response_builder.build_error("找不到 read_file 工具")

            code = read_tool.run(args)
            prompt = self._build_explain_file_prompt(
                file_path=args.get("path", ""),
                code=code,
            )
            result = self.llm_client.generate(prompt)
            return self.response_builder.build_model_result(result)

        if route_type == "project":
            tool = self.tool_registry.get(action)
            if tool is None:
                return self.response_builder.build_error(f"找不到工具: {action}")

            project_data = tool.run(args)
            self.session_state.add_recent_tool(action)

            path = args.get("path")
            if path:
                self.session_state.add_recent_file(path)

            prompt = self._build_project_prompt(
                user_text=text,
                project_data=project_data,
            )
            result = self.llm_client.generate(prompt)
            return self.response_builder.build_model_result(result)

        if route_type == "project_summary":
            tool = self.tool_registry.get(action)
            if tool is None:
                return self.response_builder.build_error(f"找不到工具: {action}")

            project_data = tool.run(args)
            self.session_state.add_recent_tool(action)

            path = args.get("path")
            if path:
                self.session_state.add_recent_file(path)

            prompt = self._build_project_summary_prompt(
                user_text=text,
                project_data=project_data,
            )
            result = self.llm_client.generate(prompt)
            return self.response_builder.build_model_result(result)

        if route_type == "fix_code":
            tool = self.tool_registry.get(action)
            if tool is None:
                return self.response_builder.build_error(f"找不到工具: {action}")

            context_data = tool.run(args)
            self.session_state.add_recent_tool(action)

            prompt = self._build_fix_code_prompt(
                user_text=text,
                context_data=context_data,
            )
            result = self.llm_client.generate(prompt)
            return self.response_builder.build_model_result(result)

        if route_type == "fix_error":
            return self._handle_fix_error(args)

        if route_type == "debug":
            return self._handle_debug_python(args)

        if route_type == "agent":
            if action == "debug_project":
                path = str(args.get("path", "")).strip()
                if not path:
                    return self.response_builder.build_error("沒有指定專案路徑")
                result = self.agent_loop.debug_project(path)
                return self.response_builder.build_model_result(result)

            if action == "goal":
                goal = str(args.get("goal", "")).strip()
                if not goal:
                    return self.response_builder.build_error("沒有提供目標")
                result = self.project_agent.run_goal(goal)
                return self.response_builder.build_model_result(result)

        if route_type == "code":
            prompt = self._build_code_prompt(text)
            result = self.llm_client.generate(prompt)
            return self.response_builder.build_model_result(result)

        if route_type == "chat":
            result = self.llm_client.generate(text)
            return self.response_builder.build_model_result(result)

        return self.response_builder.build_error(f"未支援的路由類型: {route_type}")

    def _route_text(self, text: str) -> dict[str, Any]:
        raw = text.strip()
        lowered = raw.lower()

        if not raw:
            return {
                "route_type": "empty",
                "action": None,
                "args": {},
                "original_text": raw,
            }

        if lowered in {"help", "?"}:
            return {
                "route_type": "system",
                "action": "help",
                "args": {},
                "original_text": raw,
            }

        if lowered in {"exit", "quit"}:
            return {
                "route_type": "system",
                "action": "exit",
                "args": {},
                "original_text": raw,
            }

        if lowered == "memory":
            return {
                "route_type": "memory",
                "action": "show",
                "args": {},
                "original_text": raw,
            }

        if lowered.startswith("remember "):
            return {
                "route_type": "memory",
                "action": "remember",
                "args": {"text": raw[len("remember "):].strip()},
                "original_text": raw,
            }

        if lowered.startswith("list files"):
            path = raw[len("list files"):].strip() or "."
            return {
                "route_type": "tool",
                "action": "list_files",
                "args": {"path": path},
                "original_text": raw,
            }

        if lowered.startswith("read file "):
            path = raw[len("read file "):].strip()
            return {
                "route_type": "tool",
                "action": "read_file",
                "args": {"path": path},
                "original_text": raw,
            }

        if lowered.startswith("write file "):
            remainder = raw[len("write file "):].strip()
            if "::" in remainder:
                path, content = remainder.split("::", 1)
                return {
                    "route_type": "tool",
                    "action": "write_file",
                    "args": {
                        "path": path.strip(),
                        "content": content.lstrip(),
                    },
                    "original_text": raw,
                }

        if lowered.startswith("run python "):
            path = raw[len("run python "):].strip()
            return {
                "route_type": "tool",
                "action": "run_python",
                "args": {"path": path},
                "original_text": raw,
            }

        if lowered.startswith("search code "):
            keyword = raw[len("search code "):].strip()
            return {
                "route_type": "tool",
                "action": "search_code",
                "args": {"keyword": keyword, "path": "."},
                "original_text": raw,
            }

        if lowered.startswith("search files "):
            keyword = raw[len("search files "):].strip()
            return {
                "route_type": "tool",
                "action": "search_files",
                "args": {"keyword": keyword, "path": "."},
                "original_text": raw,
            }

        if lowered.startswith("inspect project"):
            path = raw[len("inspect project"):].strip() or "."
            return {
                "route_type": "tool",
                "action": "inspect_project",
                "args": {"path": path},
                "original_text": raw,
            }

        if lowered.startswith("goal "):
            goal = raw[len("goal "):].strip()
            return {
                "route_type": "agent",
                "action": "goal",
                "args": {"goal": goal},
                "original_text": raw,
            }

        return {
            "route_type": "chat",
            "action": "respond",
            "args": {},
            "original_text": raw,
        }

    def _handle_fix_error(self, args: dict[str, Any]) -> str:
        parser = self.tool_registry.get("parse_error")
        read_tool = self.tool_registry.get("read_file")
        patch_tool = self.tool_registry.get("apply_patch")

        if parser is None:
            return self.response_builder.build_error("找不到 parse_error 工具")

        parsed = parser.run(args)
        self.session_state.add_recent_tool("parse_error")

        error_type = parsed.get("error_type", "")
        error_message = parsed.get("error_message", "")
        file_path = parsed.get("file_path", "")
        line_no = parsed.get("line_no", 0)
        raw_error = parsed.get("raw", args.get("text", ""))

        context_code = ""
        if file_path and read_tool is not None:
            code = read_tool.run({"path": file_path})

            if isinstance(code, str):
                lines = code.splitlines()
                if lines:
                    start = max(0, int(line_no) - 6)
                    end = min(len(lines), int(line_no) + 5)
                    context_code = "\n".join(lines[start:end])

        prompt = self._build_fix_error_prompt(
            error_type=error_type,
            error_message=error_message,
            file_path=file_path,
            line_no=line_no,
            raw_error=raw_error,
            context_code=context_code,
        )

        result = self.llm_client.generate(prompt)

        if not file_path or patch_tool is None:
            return self.response_builder.build_model_result(result)

        apply_result = patch_tool.run({
            "path": file_path,
            "content": result,
        })
        self.session_state.add_recent_tool("apply_patch")
        self.session_state.add_recent_file(file_path)

        return self.response_builder.build_model_result(
            f"AI修復完成\n\n{apply_result}"
        )

    def _handle_debug_python(self, args: dict[str, Any]) -> str:
        debug_tool = self.tool_registry.get("debug_python")

        if debug_tool is None:
            return self.response_builder.build_error("找不到 debug_python 工具")

        path = str(args.get("path", "")).strip()
        if not path:
            return self.response_builder.build_error("沒有指定 Python 檔案路徑")

        attempts: list[str] = []

        for i in range(1, 6):
            run_result = debug_tool.run({"path": path})
            self.session_state.add_recent_tool("debug_python")
            self.session_state.add_recent_file(path)

            success = bool(run_result.get("success"))
            output = str(run_result.get("output", "")).strip()

            attempts.append(f"=== 第 {i} 次執行 ===\n{output or '<無輸出>'}")

            if success:
                return self.response_builder.build_model_result(
                    "程式成功執行。\n\n" + "\n\n".join(attempts)
                )

            fix_result = self._handle_fix_error({"text": output})
            attempts.append(f"=== 第 {i} 次修復 ===\n{fix_result}")

        return self.response_builder.build_error(
            "AI 嘗試修復 5 次但仍失敗。\n\n" + "\n\n".join(attempts)
        )

    def _help_text(self) -> str:
        return (
            "可用指令:\n"
            "- help\n"
            "- exit\n"
            "- memory\n"
            "- remember 內容\n"
            "- list files [路徑]\n"
            "- read file <路徑>\n"
            "- explain file <路徑>\n"
            "- search code <關鍵字>\n"
            "- search files <關鍵字>\n"
            "- write file <路徑> :: <內容>\n"
            "- run python <路徑>\n"
            "- debug python <路徑>\n"
            "- debug project <路徑或入口>\n"
            "- analyze project [路徑]\n"
            "- summarize project [路徑]\n"
            "- inspect project [路徑]\n"
            "- fix code <關鍵字或錯誤描述>\n"
            "- fix error <Traceback 或錯誤訊息>\n"
            "- goal <工程目標>\n"
            "- 其他內容會走聊天/程式分析\n"
        )

    def _build_code_prompt(self, user_text: str) -> str:
        return (
            "你是本地工程 AI 助手。請用繁體中文回答，"
            "重點式說明問題原因、可能修法與注意事項。\n\n"
            f"使用者需求:\n{user_text}\n"
        )

    def _build_project_prompt(self, user_text: str, project_data: str) -> str:
        return (
            "你是本地工程 AI 助手。請用繁體中文分析這個專案。\n"
            "回答時請分成下面幾段：\n"
            "1. 專案用途\n"
            "2. 核心模組\n"
            "3. 目前已實作能力\n"
            "4. 明顯缺口\n"
            "5. 建議下一步\n\n"
            f"使用者指令:\n{user_text}\n\n"
            f"專案資料:\n{project_data}\n"
        )

    def _build_project_summary_prompt(self, user_text: str, project_data: str) -> str:
        return (
            "你是本地工程 AI 助手。請用繁體中文整理這個專案摘要。\n"
            "你必須只根據提供的專案結構與檔案內容回答。\n"
            "不要亂猜不存在的類別、功能、API、web framework、endpoint。\n"
            "如果資訊不足，就直接說資訊不足，不要自行補劇情。\n\n"
            "回答格式固定如下：\n"
            "1. 這個專案是做什麼的\n"
            "2. 專案主要資料夾與用途\n"
            "3. 核心執行流程\n"
            "4. 目前已經有的功能\n"
            "5. 還缺哪些重要能力\n"
            "6. 最建議的下一步\n\n"
            f"使用者指令:\n{user_text}\n\n"
            f"專案資料:\n{project_data}\n"
        )

    def _build_explain_file_prompt(self, file_path: str, code: str) -> str:
        return (
            "你是本地工程 AI 助手。請用繁體中文解釋這個檔案。\n"
            "不要亂猜 web routing、API endpoint 之類與檔案內容無關的用途。\n"
            "必須根據實際程式碼回答。\n\n"
            "回答格式：\n"
            "1. 這個檔案的用途\n"
            "2. 主要類別或函式\n"
            "3. 流程說明\n"
            "4. 重點邏輯\n"
            "5. 注意事項\n\n"
            f"檔案路徑:\n{file_path}\n\n"
            f"檔案內容:\n{code}\n"
        )

    def _build_fix_code_prompt(self, user_text: str, context_data: str) -> str:
        return (
            "你是本地工程 AI 助手。請根據提供的程式碼上下文，分析可能的問題與修法。\n"
            "不要亂猜不存在的檔案或函式。\n"
            "如果資訊不足，要直接說資訊不足。\n\n"
            "回答格式固定如下：\n"
            "1. 可能出問題的位置\n"
            "2. 問題原因分析\n"
            "3. 建議修改方向\n"
            "4. 需要再查看的檔案\n"
            "5. 一個簡短的 patch 建議\n\n"
            f"使用者需求:\n{user_text}\n\n"
            f"相關程式碼上下文:\n{context_data}\n"
        )

    def _build_fix_error_prompt(
        self,
        error_type: str,
        error_message: str,
        file_path: str,
        line_no: int,
        raw_error: str,
        context_code: str,
    ) -> str:
        return (
            "你是 Python 工程 AI 助手。\n"
            "請根據真實 traceback 與附近程式碼，直接輸出『修正後的完整檔案內容』。\n"
            "不要解釋，不要加 markdown，不要加 ```，只輸出完整程式碼。\n"
            "如果資訊不足，才輸出原始內容不要亂改。\n\n"
            f"錯誤類型:\n{error_type}\n\n"
            f"錯誤訊息:\n{error_message}\n\n"
            f"檔案:\n{file_path}\n\n"
            f"行號:\n{line_no}\n\n"
            f"原始 traceback:\n{raw_error}\n\n"
            f"附近程式碼:\n{context_code}\n"
        )