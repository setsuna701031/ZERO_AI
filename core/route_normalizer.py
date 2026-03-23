from typing import Any, Dict, Optional


class RouteNormalizer:
    """
    專門負責：
    1. 安全呼叫 router
    2. 將 router 回傳結果整理成統一格式
    """

    ALLOWED_MODES = {"chat", "tool", "command", "confirm", "system"}

    @staticmethod
    def safe_route(router: Any, user_input: str) -> Dict[str, Any]:
        if router is None:
            return {
                "success": True,
                "mode": "chat",
                "summary": "Router missing. Fallback to chat.",
                "data": {}
            }

        try:
            result = router.route(user_input)

            if isinstance(result, dict):
                return result

            return {
                "success": True,
                "mode": "chat",
                "summary": "Router returned non-dict result. Fallback to chat.",
                "data": {
                    "router_result_type": str(type(result))
                }
            }

        except Exception as e:
            return {
                "success": False,
                "mode": "system",
                "summary": "Router execution failed.",
                "data": {},
                "error": f"router_exception:{str(e)}"
            }

    @staticmethod
    def normalize(
        user_input: str,
        raw_route_result: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if not isinstance(raw_route_result, dict):
            return {
                "success": True,
                "mode": "chat",
                "summary": "Invalid router result. Fallback to chat.",
                "data": {
                    "user_input": user_input
                }
            }

        normalized: Dict[str, Any] = {
            "success": bool(raw_route_result.get("success", True)),
            "mode": raw_route_result.get("mode", "chat"),
            "summary": raw_route_result.get("summary", ""),
            "data": raw_route_result.get("data", {}),
            "error": raw_route_result.get("error")
        }

        if not isinstance(normalized["data"], dict):
            normalized["data"] = {"value": normalized["data"]}

        if normalized["mode"] not in RouteNormalizer.ALLOWED_MODES:
            normalized["mode"] = "chat"
            normalized["summary"] = "Invalid route mode. Fallback to chat."

        if not normalized["summary"]:
            if normalized["mode"] == "chat":
                normalized["summary"] = "一般對話回應"
            elif normalized["mode"] == "tool":
                normalized["summary"] = "工具執行"
            elif normalized["mode"] == "command":
                normalized["summary"] = "命令執行"
            elif normalized["mode"] == "confirm":
                normalized["summary"] = "等待確認"
            else:
                normalized["summary"] = "系統回應"

        normalized["data"]["user_input"] = user_input
        return normalized