from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from core.tools.commit_message_generator import generate_commit_message_to_outbox
from core.tools.pr_description_generator import generate_pr_description_to_outbox
from core.tools.readonly_tools import git_diff, git_status


class GitPipelineTool:
    """
    Read repository changes, generate commit/PR text, and write only github_outbox artifacts.
    """

    def __init__(self, workspace_root: Any = ".") -> None:
        self.workspace_root = workspace_root

    def execute(self, tool_input: Dict[str, Any] | None = None) -> Dict[str, Any]:
        payload = tool_input if isinstance(tool_input, dict) else {}
        repo_root = _resolve_repo_root(payload, self.workspace_root)
        task_id = str(payload.get("task_id") or _task_id_from_payload(payload) or "")
        trace_id = str(payload.get("trace_id") or "git_pipeline")

        diff_result = git_diff(
            repo_root=repo_root,
            task_id=task_id,
            trace_id=f"{trace_id}_git_diff",
        )
        if not diff_result.get("ok"):
            return _pipeline_result(
                ok=False,
                repo_root=repo_root,
                diff_result=diff_result,
                status_result={},
                analysis={},
                commit_message={},
                pr_description={},
                error=str(diff_result.get("error") or "git_diff_failed"),
            )

        status_result = git_status(
            repo_root=repo_root,
            task_id=task_id,
            trace_id=f"{trace_id}_git_status",
        )
        if not status_result.get("ok"):
            return _pipeline_result(
                ok=False,
                repo_root=repo_root,
                diff_result=diff_result,
                status_result=status_result,
                analysis={},
                commit_message={},
                pr_description={},
                error=str(status_result.get("error") or "git_status_failed"),
            )

        analysis = analyze_git_changes(
            diff_text=str(diff_result.get("stdout") or ""),
            status_text=str(status_result.get("stdout") or ""),
        )

        commit_message = generate_commit_message_to_outbox(
            diff_text=str(diff_result.get("stdout") or ""),
            summary=str(analysis.get("summary") or ""),
            changed_files=analysis.get("files"),
            workspace_root=repo_root,
            task_id=task_id,
            trace_id=f"{trace_id}_commit_message",
        )
        if not commit_message.get("ok"):
            return _pipeline_result(
                ok=False,
                repo_root=repo_root,
                diff_result=diff_result,
                status_result=status_result,
                analysis=analysis,
                commit_message=commit_message,
                pr_description={},
                error=str(commit_message.get("error") or "commit_message_failed"),
            )

        pr_description = generate_pr_description_to_outbox(
            analysis=analysis,
            commit_message=commit_message,
            workspace_root=repo_root,
            task_id=task_id,
            trace_id=f"{trace_id}_pr_description",
        )

        return _pipeline_result(
            ok=bool(pr_description.get("ok")),
            repo_root=repo_root,
            diff_result=diff_result,
            status_result=status_result,
            analysis=analysis,
            commit_message=commit_message,
            pr_description=pr_description,
            error=None if pr_description.get("ok") else str(pr_description.get("error") or "pr_description_failed"),
        )

    def run(self, tool_input: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.execute(tool_input)


def analyze_git_changes(*, diff_text: str, status_text: str) -> Dict[str, Any]:
    files: List[str] = []
    for line in str(diff_text or "").splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                path = parts[3].removeprefix("b/")
                if path and path not in files:
                    files.append(path)

    if not files:
        for line in str(status_text or "").splitlines():
            if len(line) > 3:
                path = line[3:].strip()
                if path and path not in files:
                    files.append(path)

    return {
        "files": files,
        "summary": "Analyze current repository changes and prepare commit message plus PR description artifacts.",
        "risk": "Low: the pipeline reads git state and writes only allowlisted github_outbox artifacts.",
    }


def _resolve_repo_root(payload: Dict[str, Any], fallback: Any) -> Path:
    for key in ("repo_root", "workspace_root", "cwd", "workspace"):
        value = payload.get(key)
        if value:
            return Path(value).resolve(strict=False)

    context = payload.get("context")
    if isinstance(context, dict):
        for key in ("repo_root", "workspace_root", "cwd", "workspace"):
            value = context.get(key)
            if value:
                return Path(value).resolve(strict=False)

    return Path(fallback or ".").resolve(strict=False)


def _task_id_from_payload(payload: Dict[str, Any]) -> str:
    task = payload.get("task")
    if isinstance(task, dict):
        return str(task.get("task_id") or task.get("task_name") or "").strip()
    return ""


def _pipeline_result(
    *,
    ok: bool,
    repo_root: Path,
    diff_result: Dict[str, Any],
    status_result: Dict[str, Any],
    analysis: Dict[str, Any],
    commit_message: Dict[str, Any],
    pr_description: Dict[str, Any],
    error: str | None,
) -> Dict[str, Any]:
    commit_outbox = commit_message.get("outbox_result", {}) if isinstance(commit_message, dict) else {}
    pr_outbox = pr_description.get("outbox_result", {}) if isinstance(pr_description, dict) else {}
    artifacts = {
        "commit_message": commit_outbox.get("output_path"),
        "pr_description": pr_outbox.get("output_path"),
    }

    changed_files = [
        str(path)
        for path in artifacts.values()
        if path
    ]

    return {
        "ok": bool(ok),
        "tool": "git_pipeline",
        "tool_class": "pipeline",
        "side_effect_level": "workspace_write",
        "repo_root": str(repo_root),
        "analysis": analysis,
        "artifacts": artifacts,
        "changed_files": changed_files,
        "diff_result": diff_result,
        "status_result": status_result,
        "commit_message": commit_message,
        "pr_description": pr_description,
        "summary": "generated github outbox commit message and PR description" if ok else "",
        "error": error,
        "git_commit": False,
        "git_push": False,
        "github_create_pr": False,
    }
