from __future__ import annotations

import re
from tools.base_tool import BaseTool


class ParseErrorTool(BaseTool):

    name = "parse_error"
    description = "解析 Python Traceback"

    def run(self, args: dict) -> dict:

        text = args.get("text", "")

        lines = text.splitlines()

        error_type = ""
        error_message = ""
        file_path = ""
        line_no = 0

        for line in reversed(lines):

            m = re.match(r"(\w+Error):\s*(.*)", line)

            if m:
                error_type = m.group(1)
                error_message = m.group(2)
                break

        for line in lines:

            m = re.search(r'File "(.+?)", line (\d+)', line)

            if m:
                file_path = m.group(1)
                line_no = int(m.group(2))

        return {
            "error_type": error_type,
            "error_message": error_message,
            "file_path": file_path,
            "line_no": line_no,
            "raw": text,
        }