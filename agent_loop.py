from typing import Any, Dict, Optional

from router import Router
from tool_registry import ToolRegistry


class AgentLoop:
    """
    ZERO Agent Loop

    目前流程：
    1. 接收 user_input
    2. Router 判斷走 chat 或 tool
    3. 若是 tool -> 交給 ToolRegistry 執行
    4. 若是 chat -> 先走本地 chat fallback
    5. 回傳統一格式結果

    這版先以可穩定執行為優先。
    後面可再擴充：
    - 接 LocalLLMClient
    - 多步規劃
    - 工具觀察/重試
    - memory
    - 任務分解
    """

    def __init__(
        self,
        router: Optional[Router] = None,
        tool_registry: Optional[ToolRegistry] = None,
        llm_client: Optional[Any] = None,
    ) -> None:
        self.router = router or Router()
        self.tool_registry = tool_registry or ToolRegistry()
        self.llm_client = llm_client

    def run(self, user_input: str) -> Dict[str, Any]:
        """
        Agent 主執行入口
        """
        try:
            route_result = self.router.route(user_input)

            route_type = route_result.get("route", "chat")
            target = route_result.get("target", "chat")

            if route_type == "tool":
                return self._handle_tool_route(user_input, route_result)

            return self._handle_chat_route(user_input, route_result)

        except Exception as e:
            return {
                "success": False,
                "agent": "ZERO",
                "type": "error",
                "user_input": user_input,
                "final_answer": f"AgentLoop 執行失敗: {str(e)}",
                "error": str(e),
            }

    def _handle_tool_route(
        self,
        user_input: str,
        route_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        處理工具型路由
        """
        tool_name = route_result.get("tool_name")
        tool_params = route_result.get("tool_params", {}) or {}

        tool_result = self.tool_registry.execute_tool(tool_name, tool_params)

        final_answer = self._format_tool_result_as_text(tool_result)

        return {
            "success": tool_result.get("success", False),
            "agent": "ZERO",
            "type": "tool_result",
            "route_result": route_result,
            "tool_name": tool_name,
            "tool_params": tool_params,
            "tool_result": tool_result,
            "user_input": user_input,
            "final_answer": final_answer,
        }

    def _handle_chat_route(
        self,
        user_input: str,
        route_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        處理一般聊天路由
        """
        chat_response = self._generate_chat_response(user_input)

        return {
            "success": True,
            "agent": "ZERO",
            "type": "chat_result",
            "route_result": route_result,
            "user_input": user_input,
            "final_answer": chat_response,
        }

    def _generate_chat_response(self, user_input: str) -> str:
        """
        一般聊天回應
        優先使用 llm_client，沒有的話走 fallback
        """
        if self.llm_client is not None:
            try:
                if hasattr(self.llm_client, "generate"):
                    response = self.llm_client.generate(user_input)
                    if response:
                        return str(response)

                if hasattr(self.llm_client, "chat"):
                    response = self.llm_client.chat(user_input)
                    if response:
                        return str(response)

            except Exception as e:
                return f"一般聊天模式啟動，但 LLM 呼叫失敗：{str(e)}"

        return self._fallback_chat_response(user_input)

    def _fallback_chat_response(self, user_input: str) -> str:
        """
        沒接上 LLM 時的暫時回應
        """
        clean = (user_input or "").strip()

        if not clean:
            return "你還沒有輸入內容。"

        simple_map = {
            "你好": "你好，我是 ZERO。現在已接上基礎 Router、ToolRegistry 和 web_search 工具。",
            "你是誰": "我是 ZERO，目前正在本地 Agent 架構中，已具備基礎工具路由能力。",
            "你能做什麼": "目前我可以先做基礎聊天，以及將查詢類請求導向 web_search 工具。",
        }

        if clean in simple_map:
            return simple_map[clean]

        return (
            "這個輸入目前被判定為一般聊天，而不是工具任務。"
            "如果你要我查資料，可以直接說：查一下、搜尋、幫我找。"
        )

    def _format_tool_result_as_text(self, tool_result: Dict[str, Any]) -> str:
        """
        把工具結果整理成可讀文字
        """
        if not tool_result.get("success", False):
            error_message = tool_result.get("error", "未知錯誤")
            return f"工具執行失敗：{error_message}"

        tool_name = tool_result.get("tool_name", "")
        results = tool_result.get("results", []) or []

        if tool_name == "web_search":
            return self._format_web_search_result(tool_result)

        if not results:
            return f"工具 {tool_name} 已執行完成，但沒有返回結果。"

        lines = [f"工具 {tool_name} 執行成功，共 {len(results)} 筆結果："]
        for index, item in enumerate(results, start=1):
            lines.append(f"{index}. {item}")

        return "\n".join(lines)

    def _format_web_search_result(self, tool_result: Dict[str, Any]) -> str:
        """
        將 web_search 的結果格式化
        """
        query = tool_result.get("query") or tool_result.get("input", {}).get("query", "")
        results = tool_result.get("results", []) or []
        result_count = tool_result.get("result_count", len(results))

        if not results:
            return f"已執行 web_search，但沒有找到與「{query}」相關的結果。"

        lines = [f"已為你搜尋「{query}」，共找到 {result_count} 筆結果："]

        for i, item in enumerate(results, start=1):
            title = str(item.get("title", "")).strip() or "無標題"
            url = str(item.get("url", "")).strip() or "無連結"
            snippet = str(item.get("snippet", "")).strip() or "無摘要"

            lines.append(f"{i}. {title}")
            lines.append(f"   URL: {url}")
            lines.append(f"   摘要: {snippet}")

        return "\n".join(lines)

    def run_once(self, user_input: str) -> Dict[str, Any]:
        """
        與 run() 同義，保留給未來擴充多步循環時使用
        """
        return self.run(user_input)


if __name__ == "__main__":
    agent = AgentLoop()

    test_inputs = [
        "查一下台北今天天氣",
        "搜尋 Python requests 教學",
        "幫我找 RTX 3060 VRAM 幾 GB",
        "你好",
        "你是誰",
        "幫我整理今天的工作",
        "",
    ]

    for text in test_inputs:
        print("=" * 100)
        print("USER INPUT:", repr(text))
        result = agent.run(text)
        print("RESULT TYPE:", result.get("type"))
        print("FINAL ANSWER:")
        print(result.get("final_answer"))
        print("FULL RESULT:")
        print(result)