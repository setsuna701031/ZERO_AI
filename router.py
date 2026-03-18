from typing import Any, Dict, List, Optional


class Router:
    """
    ZERO 路由器

    作用：
    1. 判斷使用者輸入應該走哪條路
    2. 目前先支援：
       - chat
       - tool:web_search
    3. 後續可擴充 memory / file / vision / execute ...
    """

    def __init__(self) -> None:
        self.web_search_keywords: List[str] = [
            "查一下",
            "查詢",
            "搜尋",
            "搜索",
            "幫我找",
            "找一下",
            "上網找",
            "查資料",
            "查規格",
            "查教學",
            "查天氣",
            "查新聞",
            "google",
            "search",
            "web search",
        ]

        self.web_search_question_signals: List[str] = [
            "是什麼",
            "多少",
            "幾個",
            "幾歲",
            "幾gb",
            "幾 g",
            "哪裡買",
            "規格",
            "教學",
            "天氣",
            "價格",
            "新聞",
            "介紹",
            "資料",
        ]

    def route(self, user_input: str) -> Dict[str, Any]:
        """
        根據使用者輸入決定路由
        """

        clean_text = self._normalize_text(user_input)

        if not clean_text:
            return {
                "route": "chat",
                "target": "chat",
                "reason": "empty_input",
                "tool_name": None,
                "tool_params": {},
                "original_input": user_input,
                "normalized_input": clean_text,
            }

        if self._should_use_web_search(clean_text):
            return {
                "route": "tool",
                "target": "tool:web_search",
                "reason": "matched_web_search_rule",
                "tool_name": "web_search",
                "tool_params": {
                    "query": self._extract_search_query(clean_text),
                    "max_results": 5,
                    "category": "general",
                },
                "original_input": user_input,
                "normalized_input": clean_text,
            }

        return {
            "route": "chat",
            "target": "chat",
            "reason": "default_chat",
            "tool_name": None,
            "tool_params": {},
            "original_input": user_input,
            "normalized_input": clean_text,
        }

    def _should_use_web_search(self, text: str) -> bool:
        """
        判斷是否應該走 web_search
        """

        lower_text = text.lower()

        for keyword in self.web_search_keywords:
            if keyword.lower() in lower_text:
                return True

        for signal in self.web_search_question_signals:
            if signal.lower() in lower_text:
                return True

        if text.endswith("?") or text.endswith("？"):
            return True

        return False

    def _extract_search_query(self, text: str) -> str:
        """
        嘗試把命令詞去掉，留下較乾淨的搜尋內容
        """

        query = text.strip()

        removable_prefixes = [
            "查一下",
            "查詢",
            "搜尋",
            "搜索",
            "幫我找",
            "找一下",
            "上網找",
            "幫我查一下",
            "幫我搜尋",
            "幫我搜索",
            "請幫我找",
            "請幫我查一下",
            "請搜尋",
            "請搜索",
            "google",
            "search",
            "web search",
        ]

        for prefix in removable_prefixes:
            if query.lower().startswith(prefix.lower()):
                query = query[len(prefix):].strip()
                break

        query = query.strip(" :：,.，。!?！？")

        if not query:
            return text.strip()

        return query

    def _normalize_text(self, text: Optional[str]) -> str:
        """
        基本輸入清理
        """
        if text is None:
            return ""

        cleaned = str(text).strip()
        if not cleaned:
            return ""

        return " ".join(cleaned.split())


if __name__ == "__main__":
    router = Router()

    test_inputs = [
        "查一下台北今天天氣",
        "搜尋 Python requests 教學",
        "幫我找 RTX 3060 VRAM 幾 GB",
        "今天天氣如何？",
        "你好",
        "你是誰",
        "",
    ]

    for text in test_inputs:
        print("=" * 80)
        print("INPUT:", repr(text))
        result = router.route(text)
        print("ROUTE RESULT:", result)