import os
import re


class SearchCodeTool:
    def run(self, query: str, cwd: str = ".", limit: int = 15, context_lines: int = 2):
        keywords = self._extract_keywords(query)
        matches = []

        for root, _, files in os.walk(cwd):
            for file in files:
                if not file.endswith(".py"):
                    continue

                path = os.path.join(root, file)

                try:
                    with open(path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                except:
                    continue

                for i, line in enumerate(lines):
                    for kw in keywords:
                        if kw in line.lower():
                            start = max(0, i - context_lines)
                            end = min(len(lines), i + context_lines + 1)

                            snippet = "".join(lines[start:end]).strip()

                            matches.append({
                                "file": path,
                                "line": i + 1,
                                "type": self._detect_type(line),
                                "code": snippet,
                                "keyword": kw
                            })

                            break

                    if len(matches) >= limit:
                        return self._build_result(matches)

        return self._build_result(matches)

    def _extract_keywords(self, query: str):
        query = query.lower()

        # 抓檔名
        files = re.findall(r"\w+\.py", query)

        # 抓關鍵字
        words = re.findall(r"[a-zA-Z_]{3,}", query)

        # 🔥 關鍵：如果有 router → 自動加 Router
        expanded = set(words)
        for w in words:
            if w.endswith("er"):
                expanded.add(w.capitalize())

        # 🔥 加 function 常見關鍵
        expanded.update(["def", "class"])

        return list(set(files) | expanded)

    def _detect_type(self, line: str):
        line = line.strip()

        if line.startswith("def "):
            return "function"
        if line.startswith("class "):
            return "class"
        if "import " in line:
            return "import"
        if "=" in line:
            return "assignment"

        return "code"

    def _build_result(self, matches):
        if not matches:
            return {
                "ok": True,
                "summary": "沒有找到相關程式碼",
                "raw": []
            }

        text = []
        text.append("=== 搜尋結果 ===")

        for m in matches:
            text.append(f"\n檔案: {m['file']}")
            text.append(f"行號: {m['line']}")
            text.append(f"類型: {m['type']}")
            text.append(f"關鍵字: {m['keyword']}")
            text.append("程式碼:")
            text.append(m["code"])

        return {
            "ok": True,
            "summary": "\n".join(text),
            "raw": matches
        }