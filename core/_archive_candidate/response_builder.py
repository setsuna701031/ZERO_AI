class ResponseBuilder:
    def build_tool_result(self, tool_name: str, result: str) -> str:
        return f"[工具:{tool_name}]\n{result}"

    def build_error(self, message: str) -> str:
        return f"[錯誤]\n{message}"

    def build_memory_result(self, result: str) -> str:
        return f"[記憶]\n{result}"

    def build_model_result(self, result: str) -> str:
        return result.strip()