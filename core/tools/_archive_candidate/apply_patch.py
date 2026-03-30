from __future__ import annotations

import ast
import shutil
from pathlib import Path

from tools.base_tool import BaseTool


class ApplyPatchTool(BaseTool):
    name = "apply_patch"
    description = "將 AI 生成的完整 Python 程式碼安全寫回檔案"

    def run(self, args: dict) -> str:
        path = str(args.get("path", "")).strip()
        new_code = str(args.get("content", "")).strip()

        if not path:
            return "缺少檔案路徑"

        if not new_code:
            return "沒有 patch 內容"

        file_path = Path(path)

        if not file_path.exists():
            return f"檔案不存在: {path}"

        # 只允許處理 .py，避免亂蓋其他檔案
        if file_path.suffix.lower() != ".py":
            return f"目前只允許套用到 Python 檔案: {path}"

        cleaned = self._extract_python_code(new_code)

        if not cleaned.strip():
            return "模型沒有回傳可用的 Python 程式碼"

        # 寫入前先做語法驗證
        try:
            ast.parse(cleaned)
        except SyntaxError as e:
            return (
                "拒絕套用 patch：模型回傳內容不是合法 Python。\n"
                f"SyntaxError: {e}"
            )

        try:
            backup_path = file_path.with_suffix(file_path.suffix + ".bak")
            shutil.copy2(file_path, backup_path)

            file_path.write_text(cleaned, encoding="utf-8")

            return (
                f"已修復檔案: {file_path}\n"
                f"備份檔案: {backup_path}"
            )
        except Exception as e:
            return f"寫入失敗: {e}"

    def _extract_python_code(self, text: str) -> str:
        """
        盡量從模型回覆中抽出純 Python 程式碼。
        支援：
        - 直接整份 Python
        - ```python ... ```
        - ``` ... ```
        其他自然語言內容會被拒絕
        """
        stripped = text.strip()

        # 優先處理 markdown code fence
        if "```python" in stripped:
            start = stripped.find("```python") + len("```python")
            end = stripped.find("```", start)
            if end != -1:
                return stripped[start:end].strip()

        if "```" in stripped:
            first = stripped.find("```") + 3
            end = stripped.find("```", first)
            if end != -1:
                maybe = stripped[first:end].strip()
                # 如果第一行像語言標記，去掉
                lines = maybe.splitlines()
                if lines and lines[0].strip().isidentifier():
                    maybe = "\n".join(lines[1:]).strip()
                return maybe

        # 沒有 code fence，就直接回原文，後面靠 ast.parse 擋掉中文說明
        return stripped