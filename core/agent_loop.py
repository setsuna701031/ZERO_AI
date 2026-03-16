from __future__ import annotations

from pathlib import Path


class AgentLoop:
    def __init__(self, tool_registry, llm_client) -> None:
        self.tool_registry = tool_registry
        self.llm_client = llm_client

    def debug_project(self, target: str, max_rounds: int = 5) -> str:
        debug_tool = self.tool_registry.get("debug_python")
        parse_tool = self.tool_registry.get("parse_error")
        read_tool = self.tool_registry.get("read_file")
        patch_tool = self.tool_registry.get("apply_patch")

        if debug_tool is None:
            return "找不到 debug_python 工具"

        if parse_tool is None:
            return "找不到 parse_error 工具"

        if read_tool is None:
            return "找不到 read_file 工具"

        if patch_tool is None:
            return "找不到 apply_patch 工具"

        entry_path = self._resolve_entry(target)
        if entry_path is None:
            return f"找不到可執行入口: {target}"

        logs: list[str] = [f"目標入口: {entry_path}"]

        for i in range(1, max_rounds + 1):
            run_result = debug_tool.run({"path": str(entry_path)})
            success = bool(run_result.get("success"))
            output = str(run_result.get("output", "")).strip()

            logs.append(f"=== 第 {i} 次執行 ===")
            logs.append(output or "<無輸出>")

            if success:
                return "\n".join(["程式成功執行。", ""] + logs)

            parsed = parse_tool.run({"text": output})
            file_path = str(parsed.get("file_path", "")).strip()
            line_no = int(parsed.get("line_no", 0) or 0)
            error_type = str(parsed.get("error_type", "")).strip()
            error_message = str(parsed.get("error_message", "")).strip()

            if not file_path:
                logs.append("無法從 traceback 解析出檔案路徑，停止。")
                return "\n".join(logs)

            code = read_tool.run({"path": file_path})
            if not isinstance(code, str) or not code.strip():
                logs.append(f"無法讀取檔案: {file_path}")
                return "\n".join(logs)

            context = self._extract_context(code, line_no)

            fixed_code = self._generate_fixed_code(
                file_path=file_path,
                line_no=line_no,
                error_type=error_type,
                error_message=error_message,
                raw_error=output,
                context_code=context,
                full_code=code,
            )

            if not fixed_code.strip():
                logs.append("模型沒有回傳內容，停止。")
                return "\n".join(logs)

            apply_result = patch_tool.run({
                "path": file_path,
                "content": fixed_code,
            })

            logs.append(f"=== 第 {i} 次修復 ===")
            logs.append(str(apply_result))

            # 如果 patch 沒有成功套用，就停止，避免越修越壞
            if not str(apply_result).startswith("已修復檔案:"):
                logs.append("patch 未通過驗證，停止。")
                return "\n".join(logs)

        logs.append(f"AI 嘗試修復 {max_rounds} 次但仍失敗。")
        return "\n".join(logs)

    def _resolve_entry(self, target: str) -> Path | None:
        raw = Path(target)

        if raw.exists():
            if raw.is_file():
                return raw.resolve()

            if raw.is_dir():
                candidates = [
                    "main.py",
                    "app.py",
                    "run.py",
                    "server.py",
                    "test.py",
                ]
                for name in candidates:
                    p = raw / name
                    if p.exists() and p.is_file():
                        return p.resolve()

                for py_file in sorted(raw.rglob("*.py")):
                    try:
                        text = py_file.read_text(encoding="utf-8", errors="ignore")
                    except Exception:
                        continue

                    if "__name__" in text and "__main__" in text:
                        return py_file.resolve()

                py_files = sorted(raw.glob("*.py"))
                if py_files:
                    return py_files[0].resolve()

        return None

    def _extract_context(self, code: str, line_no: int) -> str:
        lines = code.splitlines()
        if not lines:
            return ""

        start = max(0, line_no - 6)
        end = min(len(lines), line_no + 5)

        output: list[str] = []
        for idx in range(start, end):
            output.append(f"{idx + 1}: {lines[idx]}")
        return "\n".join(output)

    def _generate_fixed_code(
        self,
        file_path: str,
        line_no: int,
        error_type: str,
        error_message: str,
        raw_error: str,
        context_code: str,
        full_code: str,
    ) -> str:
        prompt = (
            "你是 Python 工程 AI。\n"
            "你的任務是修正一個 Python 檔案。\n"
            "你必須只輸出『修正後的完整 Python 程式碼』。\n"
            "禁止輸出解釋、禁止輸出自然語言、禁止輸出條列、禁止輸出 markdown code fence。\n"
            "如果你無法確定怎麼修，請原樣輸出原始完整程式碼，不要加任何說明文字。\n\n"
            f"檔案路徑:\n{file_path}\n\n"
            f"錯誤類型:\n{error_type}\n\n"
            f"錯誤訊息:\n{error_message}\n\n"
            f"錯誤行號:\n{line_no}\n\n"
            f"原始 traceback:\n{raw_error}\n\n"
            f"錯誤附近程式碼:\n{context_code}\n\n"
            f"完整原始檔案內容:\n{full_code}\n"
        )

        result = self.llm_client.generate(prompt)
        return result.strip()