from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.runtime.step_executor import StepExecutor
from core.runtime.task_step_executor_adapter import TaskStepExecutorAdapter
from core.tools.tool_registry import ToolRegistry


PREFIX = "[github-inbox-smoke]"
INBOX = REPO_ROOT / "workspace" / "github_inbox"
OUTBOX = REPO_ROOT / "workspace" / "github_outbox"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def main() -> int:
    INBOX.mkdir(parents=True, exist_ok=True)
    (INBOX / ".gitkeep").touch()
    issue_path = INBOX / "issue.txt"
    issue_path.write_text(
        "Issue: Please review the project update and prepare follow-up notes.\n",
        encoding="utf-8",
    )
    pass_step("wrote local github_inbox/issue.txt")

    registry = ToolRegistry(workspace_dir=str(REPO_ROOT))
    executor = StepExecutor(
        tool_registry=registry,
        workspace_root=str(REPO_ROOT / "workspace"),
    )
    adapter = TaskStepExecutorAdapter(
        step_executor=executor,
        tool_registry=registry,
        workspace=str(REPO_ROOT / "workspace"),
    )

    result = adapter.execute_task(
        {
            "id": "task_github_inbox_smoke",
            "title": "review this issue",
        }
    )
    if not result.get("ok"):
        return fail(f"task flow failed: {result}")
    pass_step("task flow completed")

    steps = result.get("steps")
    if not isinstance(steps, list) or not steps:
        return fail(f"task flow did not produce steps: {result}")
    if steps[0].get("tool_name") != "github_inbox":
        return fail(f"adapter did not route to github_inbox: {steps[0]}")
    pass_step("adapter routed matching task to github_inbox")

    pr_path = OUTBOX / "pr_description.md"
    devlog_path = OUTBOX / "devlog_entry.md"
    for path in (pr_path, devlog_path):
        if not path.exists():
            return fail(f"missing outbox artifact: {path}")
        text = path.read_text(encoding="utf-8", errors="replace")
        if "task description detected" not in text:
            return fail(f"artifact missing inbox analysis: {path}\n{text}")
    pass_step("github_outbox contains inbox review artifacts")

    output = result["results"][0]["result"]
    if output.get("git_commit") or output.get("git_push") or output.get("github_create_pr"):
        return fail(f"inbox flow attempted forbidden mutation: {output}")
    pass_step("no GitHub API, commit, or push was attempted")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
