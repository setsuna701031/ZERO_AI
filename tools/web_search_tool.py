from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests


class WebSearchTool:
    """
    ZERO Web Search Tool
    使用 DuckDuckGo Instant Answer API 作為搜尋來源
    """

    def __init__(self, timeout: int = 10) -> None:
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "web_search"

    def execute(self, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = payload or {}

        action = str(payload.get("action", "search")).strip() or "search"
        query = str(payload.get("query", "")).strip()

        if action != "search":
            return {
                "ok": False,
                "tool_name": self.name,
                "summary": f"Unsupported action for web_search: {action}",
                "changed_files": [],
                "evidence": [],
                "results": [],
                "error": "unsupported_action",
                "payload": payload,
            }

        if query == "":
            return {
                "ok": False,
                "tool_name": self.name,
                "summary": "Query is required for web search.",
                "changed_files": [],
                "evidence": [],
                "results": [],
                "error": "missing_query",
                "payload": payload,
            }

        try:
            return self._search_duckduckgo(query=query, payload=payload)
        except Exception as exc:
            return {
                "ok": False,
                "tool_name": self.name,
                "summary": f"Web search failed: {exc}",
                "changed_files": [],
                "evidence": [],
                "results": [],
                "error": "web_search_failed",
                "payload": payload,
            }

    def _search_duckduckgo(self, query: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
        }

        response = requests.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Search response is not a JSON object.")

        results: List[Dict[str, Any]] = []

        # Abstract
        abstract_text = data.get("AbstractText")
        abstract_url = data.get("AbstractURL")
        heading = data.get("Heading")

        if isinstance(abstract_text, str) and abstract_text.strip():
            results.append({
                "title": heading or query,
                "content": abstract_text.strip(),
                "url": abstract_url or "",
                "source": "duckduckgo_abstract",
            })

        # Related Topics
        related_topics = data.get("RelatedTopics", [])
        if isinstance(related_topics, list):
            for item in related_topics[:8]:
                if isinstance(item, dict):
                    text = item.get("Text")
                    first_url = item.get("FirstURL")

                    if isinstance(text, str) and text.strip():
                        results.append({
                            "title": query,
                            "content": text.strip(),
                            "url": first_url or "",
                            "source": "duckduckgo_related",
                        })

                    elif "Topics" in item and isinstance(item["Topics"], list):
                        for sub in item["Topics"][:3]:
                            if isinstance(sub, dict):
                                text = sub.get("Text")
                                first_url = sub.get("FirstURL")
                                if isinstance(text, str) and text.strip():
                                    results.append({
                                        "title": query,
                                        "content": text.strip(),
                                        "url": first_url or "",
                                        "source": "duckduckgo_related",
                                    })

        return {
            "ok": True,
            "tool_name": self.name,
            "summary": f"Web search results for '{query}'",
            "changed_files": [],
            "evidence": [],
            "results": results,
            "error": None,
            "payload": payload,
        }