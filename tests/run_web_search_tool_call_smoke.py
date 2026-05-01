from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.agent.agent_loop import AgentLoop
from core.tools.web_search_tool import WebSearchTool
from core.tools.tool_registry import ToolRegistry


PREFIX = "[web-search-tool-call-smoke]"


class SearchDemoPlanner:
    def plan(self, **_: Any) -> Dict[str, Any]:
        return {
            "ok": True,
            "intent": "tool_call",
            "tool_call": {
                "tool": "web_search",
                "args": {
                    "query": "local AI agent trace replay",
                    "limit": 3,
                },
            },
        }


class EmptySearchPlanner:
    def plan(self, **_: Any) -> Dict[str, Any]:
        return {
            "ok": True,
            "intent": "tool_call",
            "tool_call": {
                "tool": "web_search",
                "args": {
                    "query": "",
                    "limit": 3,
                },
            },
        }


class LongSearchPlanner:
    def plan(self, **_: Any) -> Dict[str, Any]:
        return {
            "ok": True,
            "intent": "tool_call",
            "tool_call": {
                "tool": "web_search",
                "args": {
                    "query": "x" * 500,
                    "limit": 3,
                },
            },
        }


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def main() -> int:
    registry = ToolRegistry(workspace_dir=str(REPO_ROOT))
    if not registry.has_tool("web_search"):
        return fail("web_search tool is not registered")
    pass_step("tool_registry can resolve web_search")

    direct_result = registry.execute_tool("web_search", {"query": "local AI agent trace replay", "limit": 3})
    if not isinstance(direct_result, dict) or direct_result.get("ok") is not True:
        return fail(f"normal query failed or crashed: {direct_result}")
    output = direct_result.get("output") if isinstance(direct_result.get("output"), dict) else {}
    if output.get("status") != "success":
        return fail(f"normal query did not return success status: {direct_result}")
    results = output.get("results")
    if not isinstance(results, list) or not results:
        return fail(f"normal query returned no results: {direct_result}")
    for item in results:
        if not isinstance(item, dict):
            return fail(f"result item is not an object: {item}")
        for key in ("title", "url", "snippet"):
            if key not in item:
                return fail(f"result missing {key}: {item}")
    pass_step("normal query returns search results")

    empty_result = registry.execute_tool("web_search", {"query": "", "limit": 3})
    empty_output = empty_result.get("output") if isinstance(empty_result, dict) else {}
    if empty_output.get("status") not in {"blocked", "failed"}:
        return fail(f"empty query was not blocked/failed: {empty_result}")
    pass_step("empty query is blocked or failed without crashing")

    long_result = registry.execute_tool("web_search", {"query": "x" * 500, "limit": 3})
    long_output = long_result.get("output") if isinstance(long_result, dict) else {}
    if long_output.get("status") not in {"blocked", "failed"}:
        return fail(f"long query was not blocked/failed: {long_result}")
    pass_step("overlong query is blocked or failed without crashing")

    searxng_result = WebSearchTool(provider="searxng", searxng_base_url="ftp://127.0.0.1:8888").execute(
        {"query": "local AI agent trace replay", "limit": 3}
    )
    if searxng_result.get("status") != "failed":
        return fail(f"SearxNG unsafe/unavailable provider did not fail safely: {searxng_result}")
    pass_step("SearxNG provider failure returns failed without crashing")

    loop = AgentLoop(
        planner=SearchDemoPlanner(),
        tool_registry=registry,
        workspace_dir=str(REPO_ROOT),
    )
    result = loop.run("run web search demo")
    if not result.get("ok"):
        return fail(f"agent loop search demo failed: {result}")
    execution = result.get("execution")
    if not isinstance(execution, dict):
        return fail(f"execution missing from search demo: {result}")
    trace = execution.get("execution_trace")
    if not isinstance(trace, list) or not trace:
        return fail(f"execution_trace missing: {execution}")
    if trace[0].get("event_type") != "tool_call" or trace[0].get("tool") != "web_search":
        return fail(f"execution_trace does not contain web_search tool_call: {trace}")
    pass_step("execution_trace records web_search tool_call")

    blocked_loop = AgentLoop(
        planner=EmptySearchPlanner(),
        tool_registry=registry,
        workspace_dir=str(REPO_ROOT),
    )
    blocked = blocked_loop.run("run empty web search")
    blocked_execution = blocked.get("execution") if isinstance(blocked, dict) else {}
    blocked_last = blocked_execution.get("last_result") if isinstance(blocked_execution, dict) else {}
    if blocked_last.get("status") not in {"blocked", "failed"}:
        return fail(f"empty query tool_call did not return blocked/failed: {blocked}")
    pass_step("blocked web_search tool_call returns structured status")

    long_loop = AgentLoop(
        planner=LongSearchPlanner(),
        tool_registry=registry,
        workspace_dir=str(REPO_ROOT),
    )
    long_blocked = long_loop.run("run long web search")
    long_execution = long_blocked.get("execution") if isinstance(long_blocked, dict) else {}
    long_last = long_execution.get("last_result") if isinstance(long_execution, dict) else {}
    if long_last.get("status") not in {"blocked", "failed"}:
        return fail(f"long query tool_call did not return blocked/failed: {long_blocked}")
    pass_step("overlong web_search tool_call returns structured status")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
