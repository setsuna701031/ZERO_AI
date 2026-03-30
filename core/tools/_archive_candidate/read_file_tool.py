import os


class ReadFileTool:
    name = "read_file"

    def run(self, path: str, max_chars: int = 20000):
        if not path or not isinstance(path, str):
            return {
                "ok": False,
                "summary": "read_file 失敗：path 無效",
                "raw": None
            }

        if not os.path.isfile(path):
            return {
                "ok": False,
                "summary": f"read_file 失敗：找不到檔案 {path}",
                "raw": None
            }

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(max_chars)

            summary = (
                f"=== 檔案內容 ===\n"
                f"檔案: {path}\n"
                f"字元數上限: {max_chars}\n"
                f"內容如下:\n\n{content}"
            )

            return {
                "ok": True,
                "summary": summary,
                "raw": {
                    "path": path,
                    "content": content
                }
            }

        except Exception as e:
            return {
                "ok": False,
                "summary": f"read_file 失敗：{type(e).__name__}: {e}",
                "raw": None
            }