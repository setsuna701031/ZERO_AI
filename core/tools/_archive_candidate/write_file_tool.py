import os


class WriteFileTool:
    name = "write_file"

    def run(self, path: str, content: str):
        if not path or not isinstance(path, str):
            return {
                "ok": False,
                "summary": "write_file 失敗：path 無效"
            }

        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            return {
                "ok": True,
                "summary": f"成功寫入檔案: {path}"
            }

        except Exception as e:
            return {
                "ok": False,
                "summary": f"write_file 失敗：{type(e).__name__}: {e}"
            }