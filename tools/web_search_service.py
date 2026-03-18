from typing import Any, Dict, Optional

from services.web_search_service import WebSearchService


class WebSearchTool:
    """
    ZERO 的 web_search 工具層
    作用：
    - 包裝 WebSearchService
    - 提供統一的 tool 介面給 Agent / Registry 呼叫
    """

    def __init__(
        self,
        mode: str = "mock",
        searxng_base_url: Optional[str] = None,
        timeout: int = 10,
        max_results: int = 5,
    ) -> None:
        self.name = "web_search"
        self.description = "搜尋網路資訊，可用於查資料、找教學、查規格、查一般資訊。"
        self.service = WebSearchService(
            mode=mode,
            searxng_base_url=searxng_base_url,
            timeout=timeout,
            max_results=max_results,
        )

    def execute(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        標準工具執行入口

        params 範例:
        {
            "query": "Python requests 教學",
            "max_results": 5,
            "category": "general"
        }
        """
        params = params or {}

        query = str(params.get("query", "")).strip()
        max_results = params.get("max_results", None)
        category = str(params.get("category", "general")).strip() or "general"

        if not query:
            return {
                "success": False,
                "tool_name": self.name,
                "error": "Missing required parameter: query",
                "input": params,
                "results": [],
                "result_count": 0,
            }

        try:
            result = self.service.search(
                query=query,
                max_results=max_results,
                category=category,
            )

            return {
                "success": result.get("success", False),
                "tool_name": self.name,
                "input": {
                    "query": query,
                    "max_results": max_results,
                    "category": category,
                },
                "mode": result.get("mode"),
                "query": result.get("query"),
                "category": result.get("category", category),
                "results": result.get("results", []),
                "result_count": result.get("result_count", 0),
                "elapsed_seconds": result.get("elapsed_seconds", 0),
                "error": result.get("error"),
            }

        except Exception as e:
            return {
                "success": False,
                "tool_name": self.name,
                "input": params,
                "error": f"WebSearchTool execution failed: {str(e)}",
                "results": [],
                "result_count": 0,
            }

    def get_tool_definition(self) -> Dict[str, Any]:
        """
        給 Agent / Tool Registry 看的工具描述
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "query": {
                    "type": "string",
                    "required": True,
                    "description": "要搜尋的關鍵字或問題",
                },
                "max_results": {
                    "type": "integer",
                    "required": False,
                    "default": 5,
                    "description": "最多回傳幾筆搜尋結果",
                },
                "category": {
                    "type": "string",
                    "required": False,
                    "default": "general",
                    "description": "搜尋分類，例如 general、news、science、it",
                },
            },
        }


if __name__ == "__main__":
    tool = WebSearchTool()

    test_cases = [
        {"query": "Python requests 教學"},
        {"query": "RTX 3060 VRAM 幾 GB", "max_results": 3},
        {"query": "台北今天天氣", "category": "general"},
        {},
    ]

    for i, case in enumerate(test_cases, start=1):
        print("=" * 80)
        print(f"TEST CASE {i}")
        print("INPUT:", case)
        result = tool.execute(case)
        print("OUTPUT:", result)