from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from core.tools.github_inbox_analyzer import analyze_inbox
from core.tools.github_inbox_reader import read_inbox
from core.tools.github_outbox import write_github_outbox_artifact


class GitHubInboxTool:
    def __init__(self, workspace_root: Any = ".") -> None:
        self.workspace_root = Path(workspace_root).resolve(strict=False)

    def execute(self, tool_input: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return execute_github_inbox(tool_registry=None, tool_input=tool_input, workspace_root=self.workspace_root)

    def run(self, tool_input: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.execute(tool_input)


def execute_github_inbox(
    *,
    tool_registry: Any = None,
    tool_input: Dict[str, Any] | None = None,
    workspace_root: Any | None = None,
) -> Dict[str, Any]:
    payload = tool_input if isinstance(tool_input, dict) else {}
    task = payload.get("task")

    root = workspace_root or _workspace_root(payload)
    reader_output = read_inbox(workspace_root=root)
    analysis = analyze_inbox(reader_output)
    task_text = _task_text(task, payload)

    outbox_task = (
        f"{task_text}\n\n"
        f"Inbox type: {reader_output.get('type')}\n"
        f"Summary: {analysis.get('summary')}\n"
        f"Review: {analysis.get('review')}"
    )
    if tool_registry is not None:
        outbox_result = tool_registry.execute_tool(
            "github_outbox",
            {
                "task": outbox_task,
                "source": "github_inbox_adapter",
            },
        )
    else:
        outbox_result = {"ok": True, "output": {"changed_files": []}}

    pr_content = _format_review(reader_output, analysis)
    devlog_content = _format_devlog(reader_output, analysis)
    pr_result = write_github_outbox_artifact(
        "pr_description",
        pr_content,
        workspace_root=root,
        task_id="github_inbox_adapter",
        trace_id="github_inbox_pr_description",
    )
    devlog_result = write_github_outbox_artifact(
        "devlog_entry",
        devlog_content,
        workspace_root=root,
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
