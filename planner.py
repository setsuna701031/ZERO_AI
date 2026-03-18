# planner.py
from typing import Any, Dict


class Planner:
    def __init__(self, debug: bool = False):
        self.debug = debug

    def plan(self, user_input: str, route: Dict[str, Any]) -> Dict[str, Any]:
        intent = route.get("intent", "chat")
        mode = route.get("mode", "direct")

        if mode == "direct":
            return self._build_direct_plan(user_input)

        if mode == "tool_call":
            return self._build_tool_plan(user_input, intent)

        return {
            "mode": "direct",
            "goal": f"直接回答使用者問題：{user_input}",
            "steps": [
                {
                    "type": "respond",
                    "instruction": "直接用繁體中文回答使用者，內容清楚、具體，不要空話。"
                }
            ]
        }

    def _build_direct_plan(self, user_input: str) -> Dict[str, Any]:
        return {
            "mode": "direct",
            "goal": f"直接回答使用者問題：{user_input}",
            "steps": [
                {
                    "type": "respond",
                    "instruction": "直接用繁體中文回答使用者，內容清楚、具體，不要空話。"
                }
            ]
        }

    def _build_tool_plan(self, user_input: str, intent: str) -> Dict[str, Any]:
        if intent == "time_query":
            return {
                "mode": "tool_call",
                "goal": f"使用工具完成任務：{user_input}",
                "steps": [
                    {
                        "type": "tool",
                        "tool": "time",
                        "input": {}
                    },
                    {
                        "type": "respond",
                        "instruction": "根據工具結果，用繁體中文整理清楚答案。"
                    }
                ]
            }

        if intent == "system_query":
            return {
                "mode": "tool_call",
                "goal": f"使用工具完成任務：{user_input}",
                "steps": [
                    {
                        "type": "tool",
                        "tool": "system_info",
                        "input": {}
                    },
                    {
                        "type": "respond",
                        "instruction": "根據工具結果，用繁體中文整理清楚答案。"
                    }
                ]
            }

        if intent == "calculator_query":
            expression = self._extract_expression(user_input)
            return {
                "mode": "tool_call",
                "goal": f"使用工具完成任務：{user_input}",
                "steps": [
                    {
                        "type": "tool",
                        "tool": "calculator",
                        "input": {
                            "expression": expression
                        }
                    },
                    {
                        "type": "respond",
                        "instruction": "根據工具結果，用繁體中文整理清楚答案。"
                    }
                ]
            }

        return {
            "mode": "direct",
            "goal": f"直接回答使用者問題：{user_input}",
            "steps": [
                {
                    "type": "respond",
                    "instruction": "直接用繁體中文回答使用者，內容清楚、具體，不要空話。"
                }
            ]
        }

    def _extract_expression(self, user_input: str) -> str:
        text = user_input.strip()

        prefixes = [
            "幫我算",
            "請幫我算",
            "計算",
            "算一下",
            "幫我計算",
        ]

        for prefix in prefixes:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break

        return text