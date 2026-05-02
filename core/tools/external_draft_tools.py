from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


GITHUB_DRAFT_FILES = (
    "workspace/github_outbox/commit_message.txt",
    "workspace/github_outbox/pr_description.md",
    "workspace/github_outbox/devlog_entry.md",
    "workspace/github_outbox/publish_plan.md",
)


class WebSearchDraftTool:
    name = "web_search_draft"

    def execute(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        payload = args if isinstance(args, dict) else {}
        query = str(payload.get("query") or "").strip()
        max_results = _safe_int(payload.get("max_results"), 3)
        max_results = max(1, min(max_results, 5))

        results = [
            {
                "title": f"Draft result {index}",
                "url": "about:blank",
                "snippet": "Placeholder result. Real web access is intentionally disabled in this draft tool.",
            }
            for index in range(1, max_results + 1)
        ]
        observation = {
            "type": "web_search_draft",
            "summary": f"Draft web search request prepared for: {query}",
            "query": query,
            "results": results,
            "network_access": False,
            "draft_only": True,
            "data": {
                "query": query,
                "results": results,
                "network_access": False,
                "draft_only": True,
            },
        }
        return {
            "ok": True,
            "status": "success",
            "tool": self.name,
            "tool_class": "read_only",
            "side_effect_level": "read_only",
            "summary": observation["summary"],
            "observation": observation,
            "network_access": False,
            "draft_only": True,
            "results": results,
            "git_commit": False,
            "git_push": False,
            "github_create_pr": False,
        }

    def run(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.execute(args)

    def invoke(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.execute(args)


class GitHubDraftBundleTool:
    name = "github_draft_bundle"

    def __init__(self, workspace_root: Any = "workspace") -> None:
        self.repo_root = _resolve_repo_root(workspace_root)
        self.workspace_root = self.repo_root / "workspace"
        self.outbox_dir = self.workspace_root / "github_outbox"

    def execute(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        payload = args if isinstance(args, dict) else {}
        unsafe_path = _unsafe_requested_path(payload)
        if unsafe_path:
            return _blocked(self.name, f"unsafe_output_path:{unsafe_path}")

        title = str(payload.get("title") or "").strip()
        summary = str(payload.get("summary") or "").strip()
        changes = _string_list(payload.get("changes"))
        validation = _string_list(payload.get("validation"))

        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        contents = {
            "commit_message.txt": _commit_message(title, summary),
            "pr_description.md": _pr_description(title, summary, changes, validation),
            "devlog_entry.md": _devlog_entry(title, summary, changes, validation),
            "publish_plan.md": _publish_plan(title),
        }

        changed_files: List[str] = []
        for filename, content in contents.items():
            target = (self.outbox_dir / filename).resolve(strict=False)
            if target.parent != self.outbox_dir.resolve(strict=False):
                return _blocked(self.name, f"unsafe_output_path:{filename}")
            target.write_text(content, encoding="utf-8")
            changed_files.append(str(target))

        files = list(GITHUB_DRAFT_FILES)
        observation = {
            "type": "github_draft_bundle",
            "summary": "Generated GitHub draft bundle in workspace/github_outbox",
            "files": files,
            "api_access": False,
            "draft_only": True,
            "data": {
                "files": files,
                "api_access": False,
                "draft_only": True,
                "git_commands_executed": False,
            },
        }
        return {
            "ok": True,
            "status": "success",
            "tool": self.name,
            "tool_class": "workspace_write",
            "side_effect_level": "workspace_write",
            "summary": observation["summary"],
            "observation": observation,
            "files": files,
            "changed_files": changed_files,
            "api_access": False,
            "draft_only": True,
            "git_commands_executed": False,
            "git_commit": False,
            "git_push": False,
            "github_create_pr": False,
        }

    def run(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.execute(args)

    def invoke(self, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.execute(args)


def _resolve_repo_root(value: Any) -> Path:
    root = Path(str(value or ".")).resolve(strict=False)
    if root.name == "workspace":
        return root.parent
    return root


def _unsafe_requested_path(payload: Dict[str, Any]) -> str:
    for key in ("path", "output_path", "output_dir", "target_path"):
        if key not in payload:
            continue
        raw = str(payload.get(key) or "").strip()
        if not raw:
            continue
        normalized = raw.replace("\\", "/").strip("/")
        if normalized not in {"workspace/github_outbox", "github_outbox"} and normalized not in GITHUB_DRAFT_FILES:
            return raw
    return ""


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _commit_message(title: str, summary: str) -> str:
    body = summary or title
    return f"{title}\n\n{body}\n"


def _pr_description(title: str, summary: str, changes: List[str], validation: List[str]) -> str:
    return "\n".join(
        [
            f"# {title}",
            "",
            "## Summary",
            summary,
            "",
            "## Changes",
            _bullet_list(changes),
            "",
            "## Validation",
            _bullet_list(validation),
            "",
            "Draft only. No GitHub API access, remote push, branch creation, merge, tag, or remote operation was performed.",
            "",
        ]
    )


def _devlog_entry(title: str, summary: str, changes: List[str], validation: List[str]) -> str:
    return "\n".join(
        [
            f"## {title}",
            "",
            summary,
            "",
            "Changes:",
            _bullet_list(changes),
            "",
            "Validation:",
            _bullet_list(validation),
            "",
            "Draft-only GitHub workflow bundle generated locally.",
            "",
        ]
    )


def _publish_plan(title: str) -> str:
    return "\n".join(
        [
            f"# Publish Plan: {title}",
            "",
            "1. Review generated draft files.",
            "2. Manually inspect repository changes.",
            "3. Use a human-approved GitHub workflow outside ZERO when ready.",
            "",
            "Safety: this draft tool did not call GitHub APIs, use tokens, run version-control commands, push, merge, delete, or force remote updates.",
            "",
        ]
    )


def _bullet_list(items: List[str]) -> str:
    if not items:
        return "- None recorded."
    return "\n".join(f"- {item}" for item in items)


def _blocked(tool: str, error: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "status": "blocked",
        "tool": tool,
        "tool_class": "workspace_write",
        "side_effect_level": "workspace_write",
        "summary": error,
        "observation": {
            "type": "tool_error",
            "summary": error,
            "data": {"reason": error},
        },
        "changed_files": [],
        "error": error,
        "git_commit": False,
        "git_push": False,
        "github_create_pr": False,
    }
