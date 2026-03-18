import os
import time
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:
    requests = None


class WebSearchService:
    """
    ZERO 本地 web search service

    支援模式：
    1. mock
       - 回傳假資料，方便測試整條 Agent 流程
    2. searxng
       - 呼叫本地或自架的 SearxNG API

    環境變數：
    - WEB_SEARCH_MODE=mock 或 searxng
    - SEARXNG_BASE_URL=http://127.0.0.1:8888
    - WEB_SEARCH_TIMEOUT=10
    - WEB_SEARCH_MAX_RESULTS=5
    - WEB_SEARCH_FALLBACK_TO_MOCK=true
    """

    def __init__(
        self,
        mode: str = "mock",
        searxng_base_url: Optional[str] = None,
        timeout: int = 10,
        max_results: int = 5,
        fallback_to_mock: bool = True,
    ) -> None:
        self.mode = os.getenv("WEB_SEARCH_MODE", mode).strip().lower()
        self.searxng_base_url = (
            os.getenv("SEARXNG_BASE_URL", searxng_base_url or "http://127.0.0.1:8888")
            .strip()
            .rstrip("/")
        )
        self.timeout = int(os.getenv("WEB_SEARCH_TIMEOUT", str(timeout)))
        self.max_results = int(os.getenv("WEB_SEARCH_MAX_RESULTS", str(max_results)))
        self.fallback_to_mock = self._to_bool(
            os.getenv("WEB_SEARCH_FALLBACK_TO_MOCK", str(fallback_to_mock))
        )

    def search(
        self,
        query: str,
        max_results: Optional[int] = None,
        category: str = "general",
    ) -> Dict[str, Any]:
        """
        執行搜尋並回傳統一格式結果
        """
        start_time = time.time()

        query = (query or "").strip()
        if not query:
            return self._error_response(
                query=query,
                mode_used=self.mode,
                error="Empty query",
                elapsed=time.time() - start_time,
            )

        actual_max_results = max_results or self.max_results
        category = (category or "general").strip().lower()

        try:
            if self.mode == "mock":
                results = self._mock_search(query=query, max_results=actual_max_results)
                elapsed = time.time() - start_time
                return self._success_response(
                    query=query,
                    category=category,
                    mode_used="mock",
                    results=results,
                    elapsed=elapsed,
                )

            if self.mode == "searxng":
                try:
                    results = self._search_searxng(
                        query=query,
                        max_results=actual_max_results,
                        category=category,
                    )
                    elapsed = time.time() - start_time
                    return self._success_response(
                        query=query,
                        category=category,
                        mode_used="searxng",
                        results=results,
                        elapsed=elapsed,
                    )
                except Exception as searxng_error:
                    if self.fallback_to_mock:
                        fallback_results = self._mock_search(
                            query=query,
                            max_results=actual_max_results,
                        )
                        elapsed = time.time() - start_time
                        response = self._success_response(
                            query=query,
                            category=category,
                            mode_used="mock_fallback",
                            results=fallback_results,
                            elapsed=elapsed,
                        )
                        response["warning"] = (
                            f"SearxNG failed, fallback to mock: {str(searxng_error)}"
                        )
                        return response

                    return self._error_response(
                        query=query,
                        mode_used="searxng",
                        error=f"SearxNG search failed: {str(searxng_error)}",
                        elapsed=time.time() - start_time,
                    )

            return self._error_response(
                query=query,
                mode_used=self.mode,
                error=f"Unsupported web search mode: {self.mode}",
                elapsed=time.time() - start_time,
            )

        except Exception as e:
            return self._error_response(
                query=query,
                mode_used=self.mode,
                error=str(e),
                elapsed=time.time() - start_time,
            )

    def _search_searxng(
        self,
        query: str,
        max_results: int,
        category: str = "general",
    ) -> List[Dict[str, Any]]:
        """
        呼叫 SearxNG API

        常見 endpoint:
        GET /search?q=xxx&format=json

        可用分類依 SearxNG 設定而異，常見如：
        - general
        - news
        - science
        - images
        - it
        """

        if requests is None:
            raise RuntimeError(
                "requests is not installed. Please install it with: pip install requests"
            )

        endpoint = f"{self.searxng_base_url}/search"

        params = {
            "q": query,
            "format": "json",
        }

        if category:
            params["categories"] = category

        response = requests.get(endpoint, params=params, timeout=self.timeout)
        response.raise_for_status()

        data = response.json()
        raw_results = data.get("results", [])

        normalized_results: List[Dict[str, Any]] = []

        for item in raw_results[:max_results]:
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", "")).strip()
            snippet = str(item.get("content", "")).strip()
            source = str(item.get("engine", "searxng")).strip()

            normalized_results.append(
                {
                    "title": title or "無標題",
                    "url": url or "",
                    "snippet": snippet or "無摘要",
                    "source": source or "searxng",
                }
            )

        return normalized_results

    def _mock_search(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """
        假搜尋結果，用來先打通流程或作 fallback
        """
        sample_results = [
            {
                "title": f"{query} - Mock Result 1",
                "url": "https://example.com/result1",
                "snippet": f"這是關於「{query}」的模擬搜尋結果 1。",
                "source": "mock",
            },
            {
                "title": f"{query} - Mock Result 2",
                "url": "https://example.com/result2",
                "snippet": f"這是關於「{query}」的模擬搜尋結果 2。",
                "source": "mock",
            },
            {
                "title": f"{query} - Mock Result 3",
                "url": "https://example.com/result3",
                "snippet": f"這是關於「{query}」的模擬搜尋結果 3。",
                "source": "mock",
            },
            {
                "title": f"{query} - Mock Result 4",
                "url": "https://example.com/result4",
                "snippet": f"這是關於「{query}」的模擬搜尋結果 4。",
                "source": "mock",
            },
            {
                "title": f"{query} - Mock Result 5",
                "url": "https://example.com/result5",
                "snippet": f"這是關於「{query}」的模擬搜尋結果 5。",
                "source": "mock",
            },
        ]
        return sample_results[:max_results]

    def _success_response(
        self,
        query: str,
        category: str,
        mode_used: str,
        results: List[Dict[str, Any]],
        elapsed: float,
    ) -> Dict[str, Any]:
        return {
            "success": True,
            "mode": mode_used,
            "query": query,
            "category": category,
            "result_count": len(results),
            "results": results,
            "elapsed_seconds": round(elapsed, 3),
            "error": None,
        }

    def _error_response(
        self,
        query: str,
        mode_used: str,
        error: str,
        elapsed: float,
    ) -> Dict[str, Any]:
        return {
            "success": False,
            "mode": mode_used,
            "query": query,
            "result_count": 0,
            "results": [],
            "error": error,
            "elapsed_seconds": round(elapsed, 3),
        }

    def _to_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


if __name__ == "__main__":
    service = WebSearchService()

    test_queries = [
        "Python requests 教學",
        "台北今天天氣",
        "RTX 3060 VRAM 幾 GB",
    ]

    print("=" * 100)
    print("CURRENT CONFIG")
    print(f"mode = {service.mode}")
    print(f"searxng_base_url = {service.searxng_base_url}")
    print(f"timeout = {service.timeout}")
    print(f"max_results = {service.max_results}")
    print(f"fallback_to_mock = {service.fallback_to_mock}")

    for q in test_queries:
        result = service.search(q)
        print("=" * 100)
        print(f"QUERY: {q}")
        print(result)