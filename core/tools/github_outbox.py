from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parents[2]
INBOX_DIR = REPO_ROOT / "workspace" / "github_inbox"
OUTBOX_DIR = REPO_ROOT / "workspace" / "github_outbox"

OUTBOX_FILES = {
    "commit_message": "commit_message.txt",
    "pr_description": "pr_description.md",
    "devlog_entry": "devlog_entry.md",
    "publish_plan": "publish_plan.md",
}
OUTBOX_ARTIFACTS = {
    "commit_message": "workspace/github_outbox/commit_message.txt",
    "pr_description": "workspace/github_outbox/pr_description.md",
    "devlog": "workspace/github_outbox/devlog.md",
    "devlog_entry": "workspace/github_outbox/devlog_entry.md",
    "publish_plan": "workspace/github_outbox/publish_plan.md",
    "review_report": "workspace/github_outbox/review_report.md",
}


class GitHubOutboxTool:
    def __init__(self, workspace_root: Any = ".") -> None:
        self.workspace_root = Path(workspace_root).resolve(strict=False)

    def execute(self, tool_input: Dict[str, Any] | None = None) -> Dict[str, Any]:
        payload = tool_input if isinstance(tool_input, dict) else {}
        task = payload.get("task", payload.get("goal", payload.get("input", "GitHub outbox task")))
        written = run(task, workspace_root=self.workspace_root)
        return {
            "ok": True,
            "tool": "github_outbox",
            "tool_class": "workspace_write",
            "side_effect_level": "workspace_write",
            "task": _task_text(task),
            "artifacts": written,
            "changed_files": list(written.values()),
            "summary": "generated local GitHub outbox artifacts",
            "git_commit": False,
            "git_push": False,
            "github_create_pr": False,
        }

    def run(self, tool_input: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.execute(tool_input)


def ensure_outbox(workspace_root: Any | None = None) -> Path:
    root = _root(workspace_root)
    inbox_dir = root / "workspace" / "github_inbox"
    outbox_dir = root / "workspace" / "github_outbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    outbox_dir.mkdir(parents=True, exist_ok=True)
    (inbox_dir / ".gitkeep").touch()
    (outbox_dir / ".gitkeep").touch()
    return outbox_dir


def write_file(filename: str, content: str, workspace_root: Any | None = None) -> Path:
    outbox = ensure_outbox(workspace_root)
    target = (outbox / filename).resolve(strict=False)
    if outbox.resolve(strict=False) not in [target.parent, *target.parents]:
        raise ValueError(f"refusing to write outside github_outbox: {filename}")
    target.write_text(str(content), encoding="utf-8")
    return target


def generate_commit_message(task: Any) -> str:
    task_text = _task_text(task)
    return (
        f"feat: prepare GitHub workflow outbox for {task_text}\n\n"
        f"- capture requested task: {task_text}\n"
        "- generate local commit and PR artifacts\n"
        "- avoid git commit, git push, and GitHub API calls\n"
    )


def generate_pr_description(task: Any) -> str:
    task_text = _task_text(task)
    return (
        f"# GitHub Workflow Outbox\n\n"
        f"## Task\n"
        f"{task_text}\n\n"
        "## Summary\n"
        "- Prepare local GitHub workflow artifacts.\n"
        "- Keep all output inside workspace/github_outbox.\n"
        "- Do not call GitHub, commit, or push.\n"
    )


def generate_devlog(task: Any) -> str:
    task_text = _task_text(task)
    return (
        "## L5-1 GitHub Inbox / Outbox\n\n"
        f"- Task: {task_text}\n"
        "- Created local outbox artifacts for review.\n"
        "- Confirmed workflow is local-only and safe by default.\n"
    )


def generate_publish_plan(task: Any) -> str:
    task_text = _task_text(task)
    return (
        "# Publish Plan\n\n"
        f"Task: {task_text}\n\n"
        "1. Review generated outbox files.\n"
        "2. Approve or edit the local artifacts manually.\n"
        "3. Commit/push only after separate human approval outside this tool.\n"
    )


def run(task: Any, workspace_root: Any | None = None) -> Dict[str, str]:
    ensure_outbox(workspace_root)
    outputs = {
        OUTBOX_FILES["commit_message"]: generate_commit_message(task),
        OUTBOX_FILES["pr_description"]: generate_pr_description(task),
        OUTBOX_FILES["devlog_entry"]: generate_devlog(task),
        OUTBOX_FILES["publish_plan"]: generate_publish_plan(task),
    }
    written: Dict[str, str] = {}
    for filename, content in outputs.items():
        written[filename] = str(write_file(filename, content, workspace_root))
    return written


def write_github_outbox_artifact(
    artifact: str,
    content: Any,
    *,
    workspace_root: Any = ".",
    task_id: str = "",
    trace_id: str = "",
) -> Dict[str, Any]:
    artifact_name = str(artifact or "").strip().lower()
    filename = {
        "commit_message": OUTBOX_FILES["commit_message"],
        "pr_description": OUTBOX_FILES["pr_description"],
        "devlog": "devlog.md",
        "devlog_entry": OUTBOX_FILES["devlog_entry"],
        "publish_plan": OUTBOX_FILES["publish_plan"],
        "review_report": "review_report.md",
    }.get(artifact_name)

    if not filename:
        return {
            "ok": False,
            "tool": "github_outbox",
            "artifact": artifact_name,
            "output_path": "",
            "changed_files": [],
            "summary": "",
            "error": f"unsupported github_outbox artifact: {artifact_name}",
            "git_commit": False,
            "git_push": False,
            "github_create_pr": False,
        }

    root = Path(workspace_root).resolve(strict=False)
    target_dir = root / "workspace" / "github_outbox"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    target.write_text("" if content is None else str(content), encoding="utf-8")
    return {
        "ok": True,
        "tool": "github_outbox",
        "artifact": artifact_name,
        "output_path": str(target),
        "changed_files": [str(target)],
        "summary": "write github outbox artifact",
        "error": None,
        "git_commit": False,
        "git_push": False,
        "github_create_pr": False,
        "task_id": task_id,
        "trace_id": trace_id,
        "trace": {
            "tool_name": "github_outbox",
            "tool_class": "workspace_write",
            "side_effect_level": "workspace_write",
            "output_path": str(target),
            "policy_decision": {"ok": True},
            "task_id": task_id,
            "trace_id": trace_id,
        },
    }


def _task_text(task: Any) -> str:
    text = str(task).strip()
    return text or "unspecified task"


def _root(workspace_root: Any | None) -> Path:
    if workspace_root is None:
        return REPO_ROOT
    return Path(workspace_root).resolve(strict=False)


def main() -> int:
    written = run("L5-1 GitHub Inbox / Outbox workflow")
    print("[github_outbox] generated local outbox artifacts")
    for filename in OUTBOX_FILES.values():
        print(f"- {written[filename]}")
    print("")
    print("No GitHub API call")
    print("No git commit")
    print("No git push")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
