from typing import Any, Dict, Optional


class ChatHandler:
    """
    專門負責：
    1. 安全呼叫 llm_client
    2. 標準化 LLM 回傳格式
    3. 提供 model / fallback / details 等資訊
    """

    @staticmethod
    def safe_chat(llm_client: Any, user_input: str) -> Dict[str, Any]:
        if llm_client is None:
            return {
                "success": False,
                "reply": "",
                "error": "llm_client_missing",
                "used_fallback": False,
                "details": [],
                "model": None,
            }

        try:
            if hasattr(llm_client, "generate"):
                result = llm_client.generate(user_input)
            elif hasattr(llm_client, "chat"):
                result = llm_client.chat(user_input)
            else:
                return {
                    "success": False,
                    "reply": "",
                    "error": "llm_client_method_missing",
                    "used_fallback": False,
                    "details": [],
                    "model": ChatHandler.read_llm_model_name(llm_client),
                }

            if isinstance(result, dict):
                reply = (
                    result.get("response")
                    or result.get("content")
                    or result.get("message")
                    or ""
                )

                model = result.get("model") or ChatHandler.read_llm_model_name(llm_client)

                return {
                    "success": bool(result.get("success", False) or result.get("ok", False)),
                    "reply": str(reply).strip(),
                    "error": result.get("error"),
                    "used_fallback": bool(result.get("used_fallback", False)),
                    "details": result.get("details", []),
                    "model": model,
                    "raw": result,
                }

            text = str(result).strip()
            if not text:
                return {
                    "success": False,
                    "reply": "",
                    "error": "llm_empty_response",
                    "used_fallback": False,
                    "details": [],
                    "model": ChatHandler.read_llm_model_name(llm_client),
                }

            return {
                "success": True,
                "reply": text,
                "error": None,
                "used_fallback": False,
                "details": [],
                "model": ChatHandler.read_llm_model_name(llm_client),
                "raw": result,
            }

        except Exception as e:
            return {
                "success": False,
                "reply": "",
                "error": f"llm_connection_failed:{str(e)}",
                "used_fallback": False,
                "details": [],
                "model": ChatHandler.read_llm_model_name(llm_client),
            }

    @staticmethod
    def read_llm_model_name(llm_client: Any) -> Optional[str]:
        if llm_client is None:
            return None

        try:
            model = getattr(llm_client, "model", None)
            if model is None:
                return None
            return str(model)
        except Exception:
            return None