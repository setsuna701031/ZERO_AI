from __future__ import annotations

from typing import Any, Dict, List


def analyze_inbox(reader_output: Dict[str, Any]) -> Dict[str, Any]:
    inbox_type = str(reader_output.get("type") or "unknown").strip().lower()
    files = reader_output.get("files") if isinstance(reader_output.get("files"), list) else []
    file_names = [str(item.get("name") or "") for item in files if isinstance(item, dict)]

    if inbox_type == "diff":
        summary = "code change detected"
        review = "Review the local inbox diff and prepare a code-change review artifact."
        suggestions = ["Inspect changed files", "Summarize implementation risk", "Prepare review notes"]
    elif inbox_type == "issue":
        summary = "task description detected"
        review = "Review the local inbox issue and prepare a task-focused response."
        suggestions = ["Clarify expected outcome", "Identify affected files", "Prepare implementation plan"]
    elif inbox_type == "pr":
        summary = "review required"
        review = "Review the local inbox pull request content and prepare review notes."
        suggestions = ["Check summary", "Check risks", "Prepare PR review output"]
    else:
        summary = "github inbox content detected"
        review = "Review the local inbox content and prepare a general analysis."
        suggestions = ["Classify inbox content", "Summarize relevant details"]

    if file_names:
        review = f"{review}\n\nFiles: {', '.join(file_names)}"

    return {
        "summary": summary,
        "review": review,
        "suggestions": suggestions,
    }
