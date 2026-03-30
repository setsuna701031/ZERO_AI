from __future__ import annotations

import subprocess
from pathlib import Path

from tools.base_tool import BaseTool


class DebugPythonTool(BaseTool):
    name = "debug_python"
    description = "執行 Python 腳本並回傳結果，適合非互動式腳本"

    def run(self, args: dict) -> dict:
        path = str(args.get("path", "")).strip()

        if not path:
            return {
                "success": False,
                "output": "沒有指定 Python 檔案路徑",
            }

        file_path = Path(path)

        if not file_path.exists():
            return {
                "success": False,
                "output": f"檔案不存在: {path}",
            }

        if not file_path.is_file():
            return {
                "success": False,
                "output": f"不是檔案: {path}",
            }

        # 避免拿互動式主程式來 debug，會卡在 input()
        if file_path.name.lower() == "main.py":
            return {
                "success": False,
                "output": (
                    "debug_python 不適合直接執行 main.py，"
                    "因為 main.py 是互動式 CLI，會等待使用者輸入而卡住。\n"
                    "請改用非互動式腳本，例如 test.py。"
                ),
            }

        try:
            result = subprocess.run(
                ["python", str(file_path)],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=str(file_path.parent) if str(file_path.parent) else None,
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "output": result.stdout.strip() or "<無輸出>",
                }

            return {
                "success": False,
                "output": result.stderr.strip() or result.stdout.strip() or "程式執行失敗，但沒有輸出錯誤訊息",
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": (
                    f"執行逾時: {path}\n"
                    "這個腳本可能是互動式程式、死循環，或執行時間過長。"
                ),
            }

        except Exception as e:
            return {
                "success": False,
                "output": f"執行失敗: {e}",
            }