from __future__ import annotations

from typing import Any, Dict, List


def flatten_result_candidates(value: Any) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            candidates.append(node)
            for key in (
                "result",
                "step_result",
                "last_step_result",
                "output",
                "data",
                "payload",
                "raw_result",
            ):
                nested = node.get(key)
                if isinstance(nested, (dict, list)):
                    walk(nested)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(value)
    return candidates


def format_result_candidate_summary(candidate: Dict[str, Any]) -> str:
    if not isinstance(candidate, dict):
        return ""

    result_type = str(candidate.get("type") or candidate.get("action") or "").strip().lower()

    if result_type == "read_file":
        content = str(candidate.get("content") or "").strip()
        if content:
            return content

    if result_type in {"command", "run_python"}:
        stdout = str(candidate.get("stdout") or "").strip()
        if stdout:
            return stdout
        stderr = str(candidate.get("stderr") or "").strip()
        if stderr:
            return stderr

    if result_type == "write_file":
        path = str(candidate.get("full_path") or candidate.get("path") or "").strip()
        content = str(candidate.get("content") or "").strip()
        if content and len(content) <= 200:
            return f"已寫入檔案：{path}\n內容：{content}".strip()
        if path:
            return f"已寫入檔案：{path}".strip()

    if result_type == "ensure_file":
        path = str(candidate.get("full_path") or candidate.get("path") or "").strip()
        if path:
            return f"已建立檔案：{path}".strip()

    if result_type == "verify":
        checked_text = str(candidate.get("checked_text") or "").strip()
        if checked_text:
            return f"verify ok\n內容：{checked_text}".strip()
        return "verify ok"

    if result_type == "noop":
        message = str(candidate.get("message") or "").strip()
        if message:
            return message

    for key in ("content", "stdout", "message", "summary", "response", "answer"):
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def build_simple_final_answer(results: List[Dict[str, Any]]) -> str:
    if not results:
        return "task finished"

    flattened: List[Dict[str, Any]] = []
    for item in results:
        flattened.extend(flatten_result_candidates(item))

    if not flattened:
        return "task finished"

    preferred_types = [
        "read_file",
        "command",
        "run_python",
        "write_file",
        "ensure_file",
        "verify",
        "noop",
    ]

    for preferred_type in preferred_types:
        for candidate in reversed(flattened):
            candidate_type = str(candidate.get("type") or candidate.get("action") or "").strip().lower()
            if candidate_type != preferred_type:
                continue
            summary = format_result_candidate_summary(candidate)
            if summary:
                return summary

    for candidate in reversed(flattened):
        summary = format_result_candidate_summary(candidate)
        if summary:
            return summary

    return "task finished"
