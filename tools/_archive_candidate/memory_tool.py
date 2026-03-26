from __future__ import annotations

from typing import Any, Dict, List

from memory_store import MemoryStore
from tools.base_tool import BaseTool


class MemoryTool(BaseTool):
    """
    ZERO memory 工具

    支援 action:
    - write
    - list
    - read
    - search

    回傳格式盡量統一成目前 ZERO execute_result 風格：
    - success
    - tool_name
    - summary
    - changed_files
    - evidence
    - results
    - error
    """

    name = "memory"
    description = "Store and retrieve local memory items."
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Memory action: write, list, read, or search"
            },
            "content": {
                "type": "string",
                "description": "Memory content to write"
            },
            "query": {
                "type": "string",
                "description": "Keyword query for memory search"
            }
        },
        "required": ["action"]
    }

    def __init__(self, memory_store: MemoryStore) -> None:
        self.memory_store = memory_store

    def run(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        errors = self.validate_arguments(arguments)
        if errors:
            return self._build_error_result(
                summary="Memory operation failed: invalid arguments.",
                error=f"invalid_arguments: {errors}"
            )

        action = str(arguments.get("action", "")).strip().lower()

        if action == "write":
            content = str(arguments.get("content", "")).strip()
            if not content:
                return self._build_error_result(
                    summary="Memory write failed: empty content.",
                    error="empty_content"
                )

            raw_result = self.memory_store.write_memory(content)
            return self._normalize_write_result(content, raw_result)

        if action == "list":
            raw_result = self.memory_store.list_memories()
            return self._normalize_list_like_result(
                action="list",
                raw_result=raw_result,
                query=None
            )

        if action == "read":
            raw_result = self.memory_store.read_memories()
            return self._normalize_list_like_result(
                action="read",
                raw_result=raw_result,
                query=None
            )

        if action == "search":
            query = str(arguments.get("query", "")).strip()
            if not query:
                return self._build_error_result(
                    summary="Memory search failed: empty query.",
                    error="empty_query"
                )

            raw_result = self.memory_store.search_memories(query)
            return self._normalize_list_like_result(
                action="search",
                raw_result=raw_result,
                query=query
            )

        return self._build_error_result(
            summary=f"Memory operation failed: unsupported action '{action}'.",
            error=f"unsupported_memory_action: {action}"
        )

    def _normalize_write_result(self, content: str, raw_result: Any) -> Dict[str, Any]:
        """
        將 memory_store.write_memory(...) 的各種回傳格式統一化
        """
        if isinstance(raw_result, dict):
            success = bool(raw_result.get("success", raw_result.get("ok", True)))
            error = raw_result.get("error")
            details = raw_result.get("details", [])

            summary = raw_result.get("summary")
            if not summary:
                if success:
                    summary = "Memory write completed."
                else:
                    summary = "Memory write failed."

            evidence = self._to_evidence_list(raw_result, fallback_items=[content])
            results = raw_result.get("results", [])
            if not isinstance(results, list):
                results = []

            return {
                "success": success,
                "tool_name": self.name,
                "summary": summary,
                "changed_files": [],
                "evidence": evidence,
                "results": results,
                "action": "write",
                "query": None,
                "error": self._normalize_error(error, details),
            }

        if isinstance(raw_result, str):
            return {
                "success": True,
                "tool_name": self.name,
                "summary": "Memory write completed.",
                "changed_files": [],
                "evidence": [raw_result] if raw_result.strip() else [content],
                "results": [{"content": content}],
                "action": "write",
                "query": None,
                "error": None,
            }

        return {
            "success": True,
            "tool_name": self.name,
            "summary": "Memory write completed.",
            "changed_files": [],
            "evidence": [content],
            "results": [{"content": content}],
            "action": "write",
            "query": None,
            "error": None,
        }

    def _normalize_list_like_result(
        self,
        action: str,
        raw_result: Any,
        query: str | None
    ) -> Dict[str, Any]:
        """
        統一處理 list/read/search 類型結果
        """
        if isinstance(raw_result, dict):
            success = bool(raw_result.get("success", raw_result.get("ok", True)))
            error = raw_result.get("error")
            details = raw_result.get("details", [])

            extracted_results = self._extract_results(raw_result)
            evidence = self._build_memory_evidence(extracted_results)

            summary = raw_result.get("summary")
            if not summary:
                if action == "search":
                    summary = f"Memory search completed for '{query}'. Found {len(extracted_results)} result(s)."
                elif action == "list":
                    summary = f"Memory list completed. Found {len(extracted_results)} item(s)."
                else:
                    summary = f"Memory read completed. Found {len(extracted_results)} item(s)."

            return {
                "success": success,
                "tool_name": self.name,
                "summary": summary,
                "changed_files": [],
                "evidence": evidence,
                "results": extracted_results,
                "action": action,
                "query": query,
                "error": self._normalize_error(error, details),
            }

        if isinstance(raw_result, list):
            extracted_results = self._normalize_result_items(raw_result)
            evidence = self._build_memory_evidence(extracted_results)

            if action == "search":
                summary = f"Memory search completed for '{query}'. Found {len(extracted_results)} result(s)."
            elif action == "list":
                summary = f"Memory list completed. Found {len(extracted_results)} item(s)."
            else:
                summary = f"Memory read completed. Found {len(extracted_results)} item(s)."

            return {
                "success": True,
                "tool_name": self.name,
                "summary": summary,
                "changed_files": [],
                "evidence": evidence,
                "results": extracted_results,
                "action": action,
                "query": query,
                "error": None,
            }

        if isinstance(raw_result, str):
            text = raw_result.strip()
            extracted_results = [{"content": text}] if text else []
            evidence = self._build_memory_evidence(extracted_results)

            if action == "search":
                summary = f"Memory search completed for '{query}'. Found {len(extracted_results)} result(s)."
            elif action == "list":
                summary = f"Memory list completed. Found {len(extracted_results)} item(s)."
            else:
                summary = f"Memory read completed. Found {len(extracted_results)} item(s)."

            return {
                "success": True,
                "tool_name": self.name,
                "summary": summary,
                "changed_files": [],
                "evidence": evidence,
                "results": extracted_results,
                "action": action,
                "query": query,
                "error": None,
            }

        return {
            "success": True,
            "tool_name": self.name,
            "summary": f"Memory {action} completed. Found 0 item(s).",
            "changed_files": [],
            "evidence": [],
            "results": [],
            "action": action,
            "query": query,
            "error": None,
        }

    def _extract_results(self, raw_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        從 memory_store 回傳中盡量抽出結果列表
        """
        for key in ("results", "items", "memories", "data"):
            value = raw_result.get(key)
            if isinstance(value, list):
                return self._normalize_result_items(value)

        # 有些 store 可能直接把單筆內容放在 content
        if "content" in raw_result and isinstance(raw_result.get("content"), str):
            return [{"content": str(raw_result.get("content", "")).strip()}]

        return []

    def _normalize_result_items(self, items: List[Any]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []

        for item in items:
            if isinstance(item, dict):
                content = self._pick_first_str(item, ["content", "text", "value", "memory"])
                if content:
                    normalized.append({
                        "content": content,
                        "id": item.get("id"),
                        "created_at": item.get("created_at"),
                    })
                else:
                    normalized.append({
                        "content": str(item),
                        "id": item.get("id"),
                        "created_at": item.get("created_at"),
                    })
            elif isinstance(item, str):
                text = item.strip()
                if text:
                    normalized.append({"content": text})
            else:
                normalized.append({"content": str(item)})

        return normalized

    def _build_memory_evidence(self, results: List[Dict[str, Any]]) -> List[str]:
        evidence: List[str] = []

        for idx, item in enumerate(results[:5], start=1):
            content = str(item.get("content", "")).strip()
            created_at = item.get("created_at")

            line = f"{idx}. {content}" if content else f"{idx}."
            if created_at:
                line += f" ({created_at})"

            evidence.append(line)

        return evidence

    def _to_evidence_list(self, raw_result: Dict[str, Any], fallback_items: List[str]) -> List[str]:
        evidence = raw_result.get("evidence")
        if isinstance(evidence, list):
            return [str(x) for x in evidence if str(x).strip()]

        details = raw_result.get("details")
        if isinstance(details, list) and details:
            return [str(x) for x in details if str(x).strip()]

        return [str(x) for x in fallback_items if str(x).strip()]

    def _normalize_error(self, error: Any, details: Any) -> str | None:
        if error is None:
            return None

        if isinstance(details, list) and details:
            return f"{error}: {details}"

        return str(error)

    def _pick_first_str(self, data: Dict[str, Any], keys: List[str]) -> str:
        for key in keys:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _build_error_result(self, summary: str, error: str) -> Dict[str, Any]:
        return {
            "success": False,
            "tool_name": self.name,
            "summary": summary,
            "changed_files": [],
            "evidence": [],
            "results": [],
            "action": None,
            "query": None,
            "error": error,
        }