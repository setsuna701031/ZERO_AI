from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


MAX_QUERY_LENGTH = 240
MAX_LIMIT = 10
SAFE_URL_SCHEMES = {"http", "https"}


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
        }


class SearchProvider:
    name = "provider"

    def search(self, *, query: str, limit: int) -> List[SearchResult]:
        raise NotImplementedError


class MockSearchProvider(SearchProvider):
    name = "mock"

    def search(self, *, query: str, limit: int) -> List[SearchResult]:
        templates = [
            (
                "Traceable local AI agents",
                "https://example.local/zero/traceable-agents",
                "Local AI agent runtimes can expose planning, tool calls, status, and replayable traces.",
            ),
            (
                "Agent execution trace replay",
                "https://example.local/zero/trace-replay",
                "A replay view helps users inspect what tools ran without executing the task again.",
            ),
            (
                "Tool call timelines for AI workflows",
                "https://example.local/zero/tool-call-timeline",
                "A timeline can show file_read, file_write, and commit steps with arguments and status.",
            ),
        ]
        results = [
            SearchResult(
                title=title,
                url=url,
                snippet=f"{snippet} Query: {query}",
            )
            for title, url, snippet in templates
        ]
        return results[:limit]


class SearxNGSearchProvider(SearchProvider):
    name = "searxng"

    def __init__(self, *, base_url: str, timeout: int = 10) -> None:
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.timeout = int(timeout)

    def search(self, *, query: str, limit: int) -> List[SearchResult]:
        if not self.base_url:
            raise RuntimeError("SearxNG base URL is not configured")
        parsed = urlparse(self.base_url)
        if parsed.scheme not in SAFE_URL_SCHEMES:
            raise RuntimeError("SearxNG base URL uses an unsafe URL scheme")

        params = urlencode({"q": query, "format": "json"})
        request = Request(
            f"{self.base_url}/search?{params}",
            headers={"Accept": "application/json", "User-Agent": "ZERO-WebSearchTool/1.0"},
            method="GET",
        )
        with urlopen(request, timeout=self.timeout) as response:
            body = response.read(1024 * 1024)

        data = json.loads(body.decode("utf-8", errors="replace"))
        raw_results = data.get("results") if isinstance(data, dict) else []
        if not isinstance(raw_results, list):
            return []

        results: List[SearchResult] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("content") or item.get("snippet") or "").strip()
            if not _is_safe_result_url(url):
                continue
            if not title and not snippet:
                continue
            results.append(
                SearchResult(
                    title=title or url,
                    url=url,
                    snippet=snippet,
                )
            )
            if len(results) >= limit:
                break
        return results


class WebSearchTool:
    name = "web_search"

    def __init__(
        self,
        *,
        provider: str | None = None,
        searxng_base_url: str | None = None,
        timeout: int = 10,
        max_query_length: int = MAX_QUERY_LENGTH,
    ) -> None:
        self.provider_name = str(provider or os.getenv("WEB_SEARCH_PROVIDER") or os.getenv("WEB_SEARCH_MODE") or "mock").strip().lower()
        self.searxng_base_url = str(searxng_base_url or os.getenv("SEARXNG_BASE_URL") or "").strip()
        self.timeout = int(os.getenv("WEB_SEARCH_TIMEOUT", str(timeout)))
        self.max_query_length = int(max_query_length)

    def execute(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        payload = args if isinstance(args, dict) else {}
        query = str(payload.get("query") or "").strip()
        limit = _normalize_limit(payload.get("limit", payload.get("max_results", 3)))

        if not query:
            return _result(
                ok=False,
                status="blocked",
                provider=self.provider_name,
                query=query,
                limit=limit,
                error="query is required",
            )

        if len(query) > self.max_query_length:
            return _result(
                ok=False,
                status="blocked",
                provider=self.provider_name,
                query=query[: self.max_query_length],
                limit=limit,
                error=f"query is too long; max length is {self.max_query_length}",
            )

        try:
            provider = self._build_provider()
            results = provider.search(query=query, limit=limit)
            safe_results = [
                result.to_dict()
                for result in results
                if _is_safe_result_url(result.url)
            ][:limit]
            return _result(
                ok=True,
                status="success",
                provider=provider.name,
                query=query,
                limit=limit,
                results=safe_results,
            )
        except Exception as exc:
            return _result(
                ok=False,
                status="failed",
                provider=self.provider_name,
                query=query,
                limit=limit,
                error=str(exc),
            )

    def run(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.execute(args)

    def invoke(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.execute(args)

    def _build_provider(self) -> SearchProvider:
        if self.provider_name in {"mock", "local"}:
            return MockSearchProvider()
        if self.provider_name == "searxng":
            return SearxNGSearchProvider(base_url=self.searxng_base_url, timeout=self.timeout)
        raise RuntimeError(f"unsupported search provider: {self.provider_name}")


def _normalize_limit(value: Any) -> int:
    try:
        limit = int(value)
    except Exception:
        limit = 3
    return max(1, min(limit, MAX_LIMIT))


def _is_safe_result_url(url: str) -> bool:
    if not url:
        return True
    parsed = urlparse(url)
    return parsed.scheme in SAFE_URL_SCHEMES


def _result(
    *,
    ok: bool,
    status: str,
    provider: str,
    query: str,
    limit: int,
    results: List[Dict[str, str]] | None = None,
    error: str | None = None,
) -> Dict[str, Any]:
    result_items = results or []
    summary = (
        f"found {len(result_items)} search result(s) for '{query}'"
        if ok
        else ""
    )
    return {
        "ok": bool(ok),
        "status": status,
        "tool": "web_search",
        "tool_class": "search",
        "side_effect_level": "none",
        "provider": provider,
        "query": query,
        "limit": limit,
        "results": result_items,
        "result_count": len(result_items),
        "summary": summary,
        "error": error,
        "changed_files": [],
        "git_commit": False,
        "git_push": False,
        "github_create_pr": False,
    }
