from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.runtime.step_executor import StepExecutor
from core.runtime.task_step_executor_adapter import TaskStepExecutorAdapter
from core.tools.github_outbox import OUTBOX_FILES
from core.tools.github_outbox_adapter import should_use_github_outbox
from core.tools.tool_registry import ToolRegistry


PREFIX = "[github-outbox-adapter-smoke]"
OUTBOX = REPO_ROOT / "workspace" / "github_outbox"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def main() -> int:
    if should_use_github_outbox({"title": "summarize project notes"}):
        return fail("plain project task incorrectly matched PR keyword")
    if not should_use_github_outbox({"type": "github_outbox", "title": "release notes"}):
        return fail("github_outbox task type did not match")
    pass_step("keyword and task type routing rules are scoped")

    task_text = "generate commit message for updating project"
    task = {
        "id": "task_github_outbox_adapter_smoke",
        "title": task_text,
    }

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

    result = adapter.execute_task(task)
    if not result.get("ok"):
        return fail(f"task flow failed: {result}")
    pass_step("task flow completed")

    steps = result.get("steps")
    if not isinstance(steps, list) or not steps:
        return fail(f"task flow did not produce steps: {result}")
    if steps[0].get("tool_name") != "github_outbox":
        return fail(f"adapter did not route to github_outbox: {steps[0]}")
    pass_step("adapter routed matching task to github_outbox")

    for filename in OUTBOX_FILES.values():
        path = OUTBOX / filename
        if not path.exists():
            return fail(f"missing outbox artifact: {path}")
        text = path.read_text(encoding="utf-8", errors="replace")
        if task_text not in text:
            return fail(f"artifact missing task text: {path}")
    pass_step("github_outbox artifacts were generated")

    output = result["results"][0]["result"].get("output", {})
    if output.get("git_commit") or output.get("git_push") or output.get("github_create_pr"):
        return fail(f"github_outbox attempted forbidden mutation: {output}")
    pass_step("no GitHub API, commit, or push was attempted")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
