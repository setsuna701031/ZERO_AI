from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.runtime.step_executor import StepExecutor
from core.runtime.task_step_executor_adapter import TaskStepExecutorAdapter
from core.tools.tool_registry import ToolRegistry


PREFIX = "[router-smoke]"
INBOX = REPO_ROOT / "workspace" / "github_inbox"
OUTBOX = REPO_ROOT / "workspace" / "github_outbox"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def build_adapter() -> TaskStepExecutorAdapter:
    registry = ToolRegistry(workspace_dir=str(REPO_ROOT))
    executor = StepExecutor(
        tool_registry=registry,
        workspace_root=str(REPO_ROOT / "workspace"),
    )
    return TaskStepExecutorAdapter(
        step_executor=executor,
        tool_registry=registry,
        workspace=str(REPO_ROOT / "workspace"),
    )


def main() -> int:
    INBOX.mkdir(parents=True, exist_ok=True)
    (INBOX / ".gitkeep").touch()
    (INBOX / "issue.txt").write_text("Issue: review this local inbox item.\n", encoding="utf-8")

    adapter = build_adapter()

    inbox_result = adapter.execute_task({"id": "router_inbox", "title": "review this issue"})
    if not inbox_result.get("ok"):
        return fail(f"inbox route failed: {inbox_result}")
    if inbox_result.get("steps", [{}])[0].get("tool_name") != "github_inbox":
        return fail(f"inbox task did not route to github_inbox: {inbox_result.get('steps')}")
    review_text = (OUTBOX / "pr_description.md").read_text(encoding="utf-8", errors="replace")
    if "GitHub Inbox Review" not in review_text:
        return fail(f"inbox route did not write review artifact:\n{review_text}")
    print(f"{PREFIX} PASS: inbox routed")

    outbox_result = adapter.execute_task({"id": "router_outbox", "title": "generate commit message"})
    if not outbox_result.get("ok"):
        return fail(f"outbox route failed: {outbox_result}")
    if outbox_result.get("steps", [{}])[0].get("tool_name") != "github_outbox":
        return fail(f"outbox task did not route to github_outbox: {outbox_result.get('steps')}")
    commit_text = (OUTBOX / "commit_message.txt").read_text(encoding="utf-8", errors="replace")
    if "generate commit message" not in commit_text:
        return fail(f"outbox route did not write commit artifact:\n{commit_text}")
    print(f"{PREFIX} PASS: outbox routed")

    fallback_result = adapter.execute_task({"id": "router_fallback", "title": "random unrelated task"})
    if not fallback_result.get("ok"):
        return fail(f"fallback failed: {fallback_result}")
    if fallback_result.get("steps", [{}])[0].get("type") != "respond":
        return fail(f"fallback did not stay on respond path: {fallback_result.get('steps')}")
    print(f"{PREFIX} PASS: fallback works")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
