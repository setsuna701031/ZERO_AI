from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from core.tools.github_inbox_analyzer import analyze_inbox
from core.tools.github_inbox_reader import read_inbox
from core.tools.github_outbox import write_github_outbox_artifact


GITHUB_INBOX_PHRASES = (
    "review",
    "analyze",
    "check pr",
    "read issue",
)


def should_use_github_inbox(task: Any = None, tool_input: Any = None) -> bool:
    task_data = task if isinstance(task, dict) else {}
    task_type = str(task_data.get("type") or task_data.get("task_type") or "").strip().lower()
    if task_type == "github_inbox":
        return True

    text = _combined_text(task, tool_input).lower()
    return any(phrase in text for phrase in GITHUB_INBOX_PHRASES)


def execute_github_inbox_if_needed(
    *,
    tool_registry: Any,
    tool_name: str = "",
    tool_input: Dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    payload = tool_input if isinstance(tool_input, dict) else {}
    task = payload.get("task")

    explicit_tool = str(tool_name or "").strip().lower() == "github_inbox"
    if not explicit_tool and not should_use_github_inbox(task=task, tool_input=payload):
        return None

    workspace_root = _workspace_root(payload)
    reader_output = read_inbox(workspace_root=workspace_root)
    analysis = analyze_inbox(reader_output)
    task_text = _task_text(task, payload)

    outbox_task = (
        f"{task_text}\n\n"
        f"Inbox type: {reader_output.get('type')}\n"
        f"Summary: {analysis.get('summary')}\n"
        f"Review: {analysis.get('review')}"
    )
    outbox_result = tool_registry.execute_tool(
        "github_outbox",
        {
            "task": outbox_task,
            "source": "github_inbox_adapter",
        },
    )

    pr_content = _format_review(reader_output, analysis)
    devlog_content = _format_devlog(reader_output, analysis)
    pr_result = write_github_outbox_artifact(
        "pr_description",
        pr_content,
        workspace_root=workspace_root,
        task_id="github_inbox_adapter",
        trace_id="github_inbox_pr_description",
    )
    devlog_result = write_github_outbox_artifact(
        "devlog_entry",
        devlog_content,
        workspace_root=workspace_root,
        task_id="github_inbox_adapter",
        trace_id="github_inbox_devlog_entry",
    )

    changed_files = []
    for result in (outbox_result.get("output", {}) if isinstance(outbox_result, dict) else {}, pr_result, devlog_result):
        if isinstance(result, dict):
            changed_files.extend(str(path) for path in result.get("changed_files", []) if path)

    return {
        "ok": True,
        "tool": "github_inbox",
        "stdout": f"github_inbox analyzed {len(reader_output.get('files', []))} file(s): {analysis.get('summary')}",
        "output_text": f"github_inbox analyzed {len(reader_output.get('files', []))} file(s): {analysis.get('summary')}",
        "reader": reader_output,
        "analysis": analysis,
        "outbox_result": outbox_result,
        "review_artifact": pr_result,
        "devlog_artifact": devlog_result,
        "changed_files": changed_files,
        "summary": analysis.get("summary"),
        "git_commit": False,
        "git_push": False,
        "github_create_pr": False,
    }


def build_github_inbox_step(task: Dict[str, Any]) -> Dict[str, Any] | None:
    if not should_use_github_inbox(task=task):
        return None
    return {
        "type": "tool",
        "tool_name": "github_inbox",
        "tool_input": {
            "task": task,
            "source": "github_inbox_adapter",
        },
    }


def _format_review(reader_output: Dict[str, Any], analysis: Dict[str, Any]) -> str:
    suggestions = analysis.get("suggestions") if isinstance(analysis.get("suggestions"), list) else []
    lines = [
        "# GitHub Inbox Review",
        "",
        f"Summary: {analysis.get('summary')}",
        "",
        str(analysis.get("review") or ""),
        "",
        "## Suggestions",
    ]
    lines.extend(f"- {item}" for item in suggestions)
    lines.extend(["", "## Inbox Type", str(reader_output.get("type") or "unknown")])
    return "\n".join(lines).strip() + "\n"


def _format_devlog(reader_output: Dict[str, Any], analysis: Dict[str, Any]) -> str:
    files = reader_output.get("files") if isinstance(reader_output.get("files"), list) else []
    file_names = [str(item.get("name") or "") for item in files if isinstance(item, dict)]
    lines = [
        "## L5-2 GitHub Inbox",
        "",
        f"- Inbox type: {reader_output.get('type')}",
        f"- Summary: {analysis.get('summary')}",
        f"- Files: {', '.join(file_names) if file_names else 'none'}",
        "- Mode: local read-only inbox; local outbox write only",
    ]
    return "\n".join(lines).strip() + "\n"


def _combined_text(task: Any = None, tool_input: Any = None) -> str:
    chunks = []
    for value in (task, tool_input):
        if isinstance(value, dict):
            for key in ("title", "goal", "input", "user_input", "task", "description", "type", "task_type"):
                if value.get(key) is not None:
                    chunks.append(str(value.get(key)))
        elif value is not None:
            chunks.append(str(value))
    return "\n".join(chunks)


def _task_text(task: Any = None, tool_input: Any = None) -> str:
    if isinstance(task, dict):
        for key in ("title", "goal", "input", "user_input", "description"):
            value = task.get(key)
            if value:
                return str(value)
    if isinstance(tool_input, dict):
        for key in ("task", "goal", "input", "description"):
            value = tool_input.get(key)
            if value:
                return str(value)
    return "github inbox review"


def _workspace_root(payload: Dict[str, Any]) -> Path:
    for key in ("workspace_root", "repo_root", "cwd", "workspace"):
        value = payload.get(key)
        if value:
            path = Path(str(value)).resolve(strict=False)
            return path.parent if path.name == "workspace" else path
    context = payload.get("context")
    if isinstance(context, dict):
        for key in ("workspace_root", "repo_root", "cwd", "workspace"):
            value = context.get(key)
            if value:
                path = Path(str(value)).resolve(strict=False)
                return path.parent if path.name == "workspace" else path
    return Path(__file__).resolve().parents[2]
