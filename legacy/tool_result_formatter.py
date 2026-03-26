from __future__ import annotations

from typing import Any, Dict, List, Optional


def extract_tool_error(tool_result: Dict[str, Any]) -> Optional[str]:
    possible_keys = ["error", "message", "details"]

    for key in possible_keys:
        value = tool_result.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

        if isinstance(value, list) and value:
            return " | ".join(str(item) for item in value)

    return None


def build_llm_error_message(llm_result: Dict[str, Any]) -> str:
    error_code = str(llm_result.get("error", "")).strip()
    details = llm_result.get("details", [])

    if error_code == "llm_connection_failed":
        if isinstance(details, list) and details:
            return f"LLM 連線失敗：{details[0]}"
        return "LLM 連線失敗。"

    if error_code == "llm_timeout":
        return "LLM 回應逾時。"

    if error_code == "llm_http_error":
        if isinstance(details, list) and details:
            return f"LLM HTTP 錯誤：{details[0]}"
        return "LLM HTTP 錯誤。"

    if error_code == "llm_invalid_json":
        return "LLM 回傳了無法解析的 JSON。"

    if error_code == "llm_empty_response":
        return "LLM 沒有回傳內容。"

    if isinstance(details, list) and details:
        return f"LLM 錯誤：{details[0]}"

    return "LLM 發生錯誤。"


def build_tool_final_answer(
    tool_name: str,
    success: bool,
    tool_result: Any,
    error_message: Optional[str],
) -> str:
    if not isinstance(tool_result, dict):
        if success and isinstance(tool_result, str) and tool_result.strip():
            return tool_result.strip()

        if not success:
            if error_message:
                return f"{tool_name} 執行失敗：{error_message}"
            return f"{tool_name} 執行失敗。"

        return f"{tool_name} 執行完成。"

    stdout_text = str(tool_result.get("stdout", "")).strip()
    stderr_text = str(tool_result.get("stderr", "")).strip()
    summary_text = str(tool_result.get("summary", "")).strip()

    if not success:
        failure_lines: List[str] = []

        if summary_text:
            failure_lines.append(summary_text)

        if stderr_text:
            failure_lines.append("stderr:")
            failure_lines.append(stderr_text)

        if not failure_lines and error_message:
            failure_lines.append(f"{tool_name} 執行失敗：{error_message}")

        if not failure_lines:
            failure_lines.append(f"{tool_name} 執行失敗。")

        return "\n".join(failure_lines)

    if stdout_text:
        if summary_text:
            return f"{summary_text}\n\n{stdout_text}"
        return stdout_text

    for key in ["final_answer", "response", "message", "output", "result"]:
        value = tool_result.get(key)
        if isinstance(value, str) and value.strip():
            if summary_text and value.strip() != summary_text:
                return f"{summary_text}\n\n{value.strip()}"
            return value.strip()

    if "data" in tool_result:
        data_value = tool_result.get("data")

        if isinstance(data_value, str) and data_value.strip():
            if summary_text:
                return f"{summary_text}\n\n{data_value.strip()}"
            return data_value.strip()

        if isinstance(data_value, list):
            body = "\n".join(str(item) for item in data_value)
            if summary_text:
                return f"{summary_text}\n\n{body}"
            return body

        if isinstance(data_value, dict):
            pretty_lines: List[str] = []
            for k, v in data_value.items():
                pretty_lines.append(f"{k}: {v}")

            if pretty_lines:
                body = "\n".join(pretty_lines)
                if summary_text:
                    return f"{summary_text}\n\n{body}"
                return body

    if stderr_text:
        if summary_text:
            return f"{summary_text}\n\nstderr:\n{stderr_text}"
        return f"stderr:\n{stderr_text}"

    if summary_text:
        return summary_text

    return f"{tool_name} 執行完成。"