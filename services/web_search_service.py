import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    requests = None


class WebSearchService:
    """
    ZERO 本地 web search service（搜尋品質優化版）

    支援模式：
    1. mock
    2. searxng

    功能重點：
    - 中文查詢優化
    - 根據問題內容自動判斷搜尋策略
    - 自動補語言參數
    - 過濾低品質結果
    - 統一輸出格式
    - searxng 失敗時可 fallback 到 mock

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

        self.bad_domains = {
            "example.com",
        }

        self.low_value_domains = {
            "reddit.com",
            "www.reddit.com",
            "m.reddit.com",
            "quora.com",
            "www.quora.com",
        }

    def search(
        self,
        query: str,
        max_results: Optional[int] = None,
        category: str = "general",
    ) -> Dict[str, Any]:
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

        try:
            intent = self._detect_search_intent(query)
            optimized_query, optimized_category, language = self._build_search_plan(
                query=query,
                requested_category=category,
                detected_intent=intent,
            )

            if self.mode == "mock":
                results = self._mock_search(
                    query=optimized_query,
                    max_results=actual_max_results,
                )
                elapsed = time.time() - start_time
                response = self._success_response(
                    query=query,
                    category=optimized_category,
                    mode_used="mock",
                    results=results,
                    elapsed=elapsed,
                )
                response["optimized_query"] = optimized_query
                response["language"] = language
                response["intent"] = intent
                return response

            if self.mode == "searxng":
                try:
                    results = self._search_searxng(
                        query=optimized_query,
                        max_results=actual_max_results,
                        category=optimized_category,
                        language=language,
                    )

                    cleaned_results = self._clean_and_rank_results(
                        original_query=query,
                        intent=intent,
                        results=results,
                        max_results=actual_max_results,
                    )

                    elapsed = time.time() - start_time
                    response = self._success_response(
                        query=query,
                        category=optimized_category,
                        mode_used="searxng",
                        results=cleaned_results,
                        elapsed=elapsed,
                    )
                    response["optimized_query"] = optimized_query
                    response["language"] = language
                    response["intent"] = intent
                    return response

                except Exception as searxng_error:
                    if self.fallback_to_mock:
                        fallback_results = self._mock_search(
                            query=optimized_query,
                            max_results=actual_max_results,
                        )
                        elapsed = time.time() - start_time
                        response = self._success_response(
                            query=query,
                            category=optimized_category,
                            mode_used="mock_fallback",
                            results=fallback_results,
                            elapsed=elapsed,
                        )
                        response["warning"] = (
                            f"SearxNG failed, fallback to mock: {str(searxng_error)}"
                        )
                        response["optimized_query"] = optimized_query
                        response["language"] = language
                        response["intent"] = intent
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
        language: str = "auto",
    ) -> List[Dict[str, Any]]:
        if requests is None:
            raise RuntimeError(
                "requests is not installed. Please install it with: pip install requests"
            )

        endpoint = f"{self.searxng_base_url}/search"
        params = {
            "q": query,
            "format": "json",
            "categories": category,
            "language": language,
        }

        response = requests.get(endpoint, params=params, timeout=self.timeout)
        response.raise_for_status()

        data = response.json()
        raw_results = data.get("results", [])

        normalized_results: List[Dict[str, Any]] = []

        for item in raw_results[: max_results * 4]:
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", "")).strip()
            snippet = str(item.get("content", "")).strip()
            source = str(item.get("engine", "searxng")).strip()

            normalized_results.append(
                {
                    "title": title or "無標題",
                    "url": url,
                    "snippet": snippet or "無摘要",
                    "source": source or "searxng",
                    "domain": self._extract_domain(url),
                }
            )

        return normalized_results

    def _detect_search_intent(self, query: str) -> str:
        q = query.lower()

        weather_keywords = ["天氣", "氣溫", "下雨", "降雨", "溫度", "weather", "forecast"]
        news_keywords = ["新聞", "最新", "消息", "news", "headline"]
        tutorial_keywords = ["教學", "怎麼", "如何", "使用", "tutorial", "guide", "how to"]
        spec_keywords = ["規格", "參數", "配置", "幾gb", "幾 gb", "尺寸", "spec", "specs"]
        shopping_keywords = ["價格", "多少錢", "哪裡買", "購買", "價錢", "price", "buy"]

        if any(k in q for k in weather_keywords):
            return "weather"
        if any(k in q for k in news_keywords):
            return "news"
        if any(k in q for k in tutorial_keywords):
            return "tutorial"
        if any(k in q for k in spec_keywords):
            return "spec"
        if any(k in q for k in shopping_keywords):
            return "shopping"
        return "general"

    def _build_search_plan(
        self,
        query: str,
        requested_category: str,
        detected_intent: str,
    ) -> Tuple[str, str, str]:
        clean_query = self._normalize_query_text(query)
        language = self._detect_language(clean_query)
        category = (requested_category or "general").strip().lower() or "general"

        if detected_intent == "weather":
            category = "general"
            optimized_query = self._build_weather_query(clean_query)
            language = self._prefer_zh_language(language)
            return optimized_query, category, language

        if detected_intent == "news":
            category = "news"
            optimized_query = self._build_news_query(clean_query)
            language = self._prefer_zh_language(language)
            return optimized_query, category, language

        if detected_intent == "tutorial":
            category = "general"
            optimized_query = self._build_tutorial_query(clean_query)
            return optimized_query, category, language

        if detected_intent == "spec":
            category = "general"
            optimized_query = self._build_spec_query(clean_query)
            return optimized_query, category, language

        if detected_intent == "shopping":
            category = "general"
            optimized_query = self._build_shopping_query(clean_query)
            return optimized_query, category, language

        optimized_query = clean_query
        return optimized_query, category, language

    def _build_weather_query(self, query: str) -> str:
        city = self._extract_location_from_weather_query(query)
        if city:
            return f"{city} 天氣 預報 氣溫 降雨"
        return f"{query} 天氣 預報"

    def _build_news_query(self, query: str) -> str:
        stripped = self._remove_common_command_prefixes(query)
        if "新聞" in stripped:
            return stripped
        return f"{stripped} 最新 新聞"

    def _build_tutorial_query(self, query: str) -> str:
        stripped = self._remove_common_command_prefixes(query)
        extra_terms = ["教學", "指南"]
        if any(term in stripped for term in extra_terms):
            return stripped
        return f"{stripped} 教學"

    def _build_spec_query(self, query: str) -> str:
        stripped = self._remove_common_command_prefixes(query)
        extra_terms = ["規格", "參數", "spec"]
        if any(term.lower() in stripped.lower() for term in extra_terms):
            return stripped
        return f"{stripped} 規格"

    def _build_shopping_query(self, query: str) -> str:
        stripped = self._remove_common_command_prefixes(query)
        extra_terms = ["價格", "價錢", "price"]
        if any(term.lower() in stripped.lower() for term in extra_terms):
            return stripped
        return f"{stripped} 價格"

    def _clean_and_rank_results(
        self,
        original_query: str,
        intent: str,
        results: List[Dict[str, Any]],
        max_results: int,
    ) -> List[Dict[str, Any]]:
        cleaned: List[Dict[str, Any]] = []
        seen_urls = set()
        query_terms = self._tokenize_query(original_query)

        for item in results:
            url = str(item.get("url", "")).strip()
            title = str(item.get("title", "")).strip()
            snippet = str(item.get("snippet", "")).strip()
            domain = str(item.get("domain", "")).strip().lower()

            if not url or url in seen_urls:
                continue

            if domain in self.bad_domains:
                continue

            if self._is_low_quality_result(title=title, snippet=snippet, url=url):
                continue

            score = self._score_result(
                intent=intent,
                query_terms=query_terms,
                title=title,
                snippet=snippet,
                domain=domain,
            )

            cleaned_item = {
                "title": title or "無標題",
                "url": url,
                "snippet": snippet or "無摘要",
                "source": item.get("source", "searxng"),
                "domain": domain,
                "_score": score,
            }

            cleaned.append(cleaned_item)
            seen_urls.add(url)

        cleaned.sort(key=lambda x: x["_score"], reverse=True)

        final_results: List[Dict[str, Any]] = []
        for item in cleaned[:max_results]:
            item.pop("_score", None)
            final_results.append(item)

        return final_results

    def _score_result(
        self,
        intent: str,
        query_terms: List[str],
        title: str,
        snippet: str,
        domain: str,
    ) -> int:
        score = 0
        haystack = f"{title} {snippet}".lower()

        for term in query_terms:
            if term.lower() in haystack:
                score += 5

        if intent == "weather":
            if any(word in haystack for word in ["天氣", "氣溫", "降雨", "forecast", "weather"]):
                score += 15
            if any(word in domain for word in ["weather", "cwa", "accuweather"]):
                score += 15

        if intent == "news":
            if any(word in haystack for word in ["新聞", "最新", "快訊", "news"]):
                score += 15

        if intent == "tutorial":
            if any(word in haystack for word in ["教學", "指南", "guide", "tutorial", "how to"]):
                score += 15

        if intent == "spec":
            if any(word in haystack for word in ["規格", "參數", "記憶體", "vram", "gb", "spec"]):
                score += 15

        if intent == "shopping":
            if any(word in haystack for word in ["價格", "價錢", "售價", "price"]):
                score += 15

        if domain in self.low_value_domains:
            score -= 10

        if title and snippet:
            score += 3

        return score

    def _is_low_quality_result(self, title: str, snippet: str, url: str) -> bool:
        combined = f"{title} {snippet}".strip().lower()

        if not title and not snippet:
            return True

        if len(combined) < 8:
            return True

        if "mock result" in combined:
            return True

        if "javascript is disabled" in combined:
            return True

        if not url.startswith("http://") and not url.startswith("https://"):
            return True

        return False

    def _extract_location_from_weather_query(self, query: str) -> str:
        candidates = [
            "台北", "新北", "桃園", "台中", "臺中", "台南", "臺南", "高雄",
            "基隆", "新竹", "苗栗", "彰化", "南投", "雲林", "嘉義",
            "屏東", "宜蘭", "花蓮", "台東", "臺東", "澎湖", "金門", "連江",
            "taipei", "taichung", "tainan", "kaohsiung",
        ]

        for city in candidates:
            if city.lower() in query.lower():
                return city
        return ""

    def _detect_language(self, query: str) -> str:
        if re.search(r"[\u4e00-\u9fff]", query):
            return "zh-TW"
        return "auto"

    def _prefer_zh_language(self, current_language: str) -> str:
        if current_language == "auto":
            return "zh-TW"
        return current_language

    def _normalize_query_text(self, text: str) -> str:
        text = self._remove_common_command_prefixes(text)
        text = text.strip(" \t\r\n:：,，。!?！？")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _remove_common_command_prefixes(self, text: str) -> str:
        prefixes = [
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
        ]

        result = text.strip()
        for prefix in prefixes:
            if result.startswith(prefix):
                result = result[len(prefix):].strip()
                break
        return result

    def _tokenize_query(self, query: str) -> List[str]:
        query = self._normalize_query_text(query)
        zh_chunks = re.findall(r"[\u4e00-\u9fff]{1,}", query)
        en_chunks = re.findall(r"[A-Za-z0-9\-\._]+", query)

        tokens: List[str] = []

        for chunk in zh_chunks:
            if len(chunk) >= 2:
                tokens.append(chunk)

        for chunk in en_chunks:
            if len(chunk) >= 2:
                tokens.append(chunk)

        return tokens[:10]

    def _extract_domain(self, url: str) -> str:
        try:
            return urlparse(url).netloc.lower().strip()
        except Exception:
            return ""

    def _mock_search(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        sample_results = [
            {
                "title": f"{query} - Mock Result 1",
                "url": "https://example.com/result1",
                "snippet": f"這是關於「{query}」的模擬搜尋結果 1。",
                "source": "mock",
                "domain": "example.com",
            },
            {
                "title": f"{query} - Mock Result 2",
                "url": "https://example.com/result2",
                "snippet": f"這是關於「{query}」的模擬搜尋結果 2。",
                "source": "mock",
                "domain": "example.com",
            },
            {
                "title": f"{query} - Mock Result 3",
                "url": "https://example.com/result3",
                "snippet": f"這是關於「{query}」的模擬搜尋結果 3。",
                "source": "mock",
                "domain": "example.com",
            },
            {
                "title": f"{query} - Mock Result 4",
                "url": "https://example.com/result4",
                "snippet": f"這是關於「{query}」的模擬搜尋結果 4。",
                "source": "mock",
                "domain": "example.com",
            },
            {
                "title": f"{query} - Mock Result 5",
                "url": "https://example.com/result5",
                "snippet": f"這是關於「{query}」的模擬搜尋結果 5。",
                "source": "mock",
                "domain": "example.com",
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
        "查一下台北今天天氣",
        "搜尋 Python requests 教學",
        "幫我找 RTX 3060 VRAM 幾 GB",
        "最新 AI 新聞",
        "ChatGPT 使用教學",
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