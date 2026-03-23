from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple
from urllib.parse import urlparse

import requests


class LocalWebSearch:
    """
    ZERO 本地 Web Search

    支援模式：
    1. mock
    2. searxng
    """

    def __init__(
        self,
        mode: str = "mock",
        searxng_base_url: str = "http://127.0.0.1:8888",
        timeout: int = 10,
        max_results: int = 5,
        language: str = "zh-TW",
        safesearch: int = 1,
    ) -> None:
        self.mode = mode
        self.searxng_base_url = searxng_base_url.rstrip("/")
        self.timeout = timeout
        self.max_results = max_results
        self.language = language
        self.safesearch = safesearch

        self.low_quality_domains: Set[str] = {
            "baike.baidu.com",
            "baike.sogou.com",
            "zhidao.baidu.com",
        }

        self.preferred_domains: Set[str] = {
            "python.org",
            "docs.python.org",
            "developer.nvidia.com",
            "nvidia.com",
            "www.nvidia.com",
            "github.com",
            "docs.github.com",
            "readthedocs.io",
            "stackoverflow.com",
            "w3schools.com",
            "www.w3schools.com",
            "w3schools.com.cn",
            "www.w3schools.com.cn",
            "runoob.com",
            "www.runoob.com",
            "techpowerup.com",
            "www.techpowerup.com",
        }

    def search(self, query: str) -> Dict[str, Any]:
        query = (query or "").strip()

        if not query:
            return {
                "ok": False,
                "error": "empty_query",
                "results": [],
            }

        if self.mode == "mock":
            return self._mock_search(query)

        if self.mode == "searxng":
            return self._searxng_search(query)

        return {
            "ok": False,
            "error": "unsupported_search_mode",
            "mode": self.mode,
            "results": [],
        }

    def _mock_search(self, query: str) -> Dict[str, Any]:
        fake_results: List[Dict[str, str]] = [
            {
                "title": f"Mock result 1 for: {query}",
                "url": "https://example.com/result1",
                "snippet": f"This is a mock snippet for query: {query}",
            },
            {
                "title": f"Mock result 2 for: {query}",
                "url": "https://example.com/result2",
                "snippet": f"Another mock snippet for query: {query}",
            },
        ]

        return {
            "ok": True,
            "backend": "local_web_search_mock",
            "query": query,
            "results": fake_results,
        }

    def _searxng_search(self, query: str) -> Dict[str, Any]:
        url = f"{self.searxng_base_url}/search"
        params = {
            "q": query,
            "format": "json",
            "language": self.language,
            "safesearch": self.safesearch,
        }

        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            return {
                "ok": False,
                "backend": "searxng",
                "query": query,
                "error": "request_timeout",
                "details": [f"SearxNG request timed out after {self.timeout} seconds"],
                "results": [],
            }
        except requests.exceptions.ConnectionError:
            return {
                "ok": False,
                "backend": "searxng",
                "query": query,
                "error": "connection_failed",
                "details": [f"Cannot connect to SearxNG at {url}"],
                "results": [],
            }
        except requests.exceptions.HTTPError as exc:
            return {
                "ok": False,
                "backend": "searxng",
                "query": query,
                "error": "http_error",
                "details": [str(exc)],
                "results": [],
            }
        except requests.exceptions.RequestException as exc:
            return {
                "ok": False,
                "backend": "searxng",
                "query": query,
                "error": "request_failed",
                "details": [str(exc)],
                "results": [],
            }

        try:
            data = response.json()
        except ValueError:
            return {
                "ok": False,
                "backend": "searxng",
                "query": query,
                "error": "invalid_json_response",
                "details": ["SearxNG did not return valid JSON"],
                "results": [],
            }

        raw_results = data.get("results", [])
        normalized_results = self._normalize_searxng_results(raw_results)
        filtered_results = self._filter_and_rank_results(normalized_results)

        return {
            "ok": True,
            "backend": "searxng",
            "query": query,
            "result_count": len(filtered_results),
            "results": filtered_results[: self.max_results],
        }

    def _normalize_searxng_results(self, raw_results: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        normalized: List[Dict[str, str]] = []

        for item in raw_results:
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", "")).strip()
            snippet = str(item.get("content", "")).strip()

            normalized.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                }
            )

        return normalized

    def _filter_and_rank_results(self, results: List[Dict[str, str]]) -> List[Dict[str, str]]:
        cleaned: List[Dict[str, str]] = []
        seen_urls: Set[str] = set()

        for item in results:
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            snippet = item.get("snippet", "").strip()

            if not title or not url:
                continue

            normalized_url = self._normalize_url_for_dedup(url)
            if normalized_url in seen_urls:
                continue

            seen_urls.add(normalized_url)

            cleaned.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                }
            )

        scored: List[Tuple[int, Dict[str, str]]] = []

        for item in cleaned:
            score = self._score_result(item)
            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [item for score, item in scored]

    def _score_result(self, item: Dict[str, str]) -> int:
        title = item.get("title", "").lower()
        url = item.get("url", "")
        snippet = item.get("snippet", "").lower()
        domain = self._extract_domain(url)

        score = 0

        if domain in self.preferred_domains:
            score += 30

        if domain in self.low_quality_domains:
            score -= 20

        if domain.endswith(".jp") or domain.endswith(".ru"):
            score -= 8

        if "docs" in domain or "documentation" in title or "說明文件" in title or "文档" in title:
            score += 15

        if "official" in title or "官网" in title or "官方" in title:
            score += 15

        if "tutorial" in title or "教學" in title or "教程" in title:
            score += 10

        if "python" in title or "python" in snippet:
            score += 5

        if "rtx 3060" in title or "rtx 3060" in snippet:
            score += 5

        if len(snippet) > 40:
            score += 3

        return score

    def _extract_domain(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except Exception:
            return ""

    def _normalize_url_for_dedup(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            scheme = parsed.scheme.lower()
            netloc = parsed.netloc.lower()
            path = parsed.path.rstrip("/")
            return f"{scheme}://{netloc}{path}"
        except Exception:
            return url.strip().lower()