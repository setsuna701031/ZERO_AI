from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.runtime.step_executor import StepExecutor
from core.runtime.task_step_executor_adapter import TaskStepExecutorAdapter
from core.tools.github_outbox import OUTBOX_FILES
from core.tools.tool_registry import ToolRegistry


PREFIX = "[execution-session-smoke]"
SESSION_DIR = REPO_ROOT / "workspace" / "execution_sessions"
OUTBOX = REPO_ROOT / "workspace" / "github_outbox"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def session_files() -> set[Path]:
    if not SESSION_DIR.exists():
        return set()
    return set(SESSION_DIR.glob("*.json"))


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
    before = session_files()
    task_text = "generate commit message for session test"

    result = build_adapter().execute_task(
        {
            "id": "task_execution_session_smoke",
            "title": task_text,
        }
    )
    if not result.get("ok"):
        return fail(f"task flow failed: {result}")
    pass_step("task flow completed")

    after = session_files()
    created = sorted(after - before, key=lambda path: path.stat().st_mtime, reverse=True)
    if not created:
        return fail(f"no execution session json created in {SESSION_DIR}")

    session_path = created[0]
    session = json.loads(session_path.read_text(encoding="utf-8"))
    for key in ("session_id", "task_summary", "status", "steps", "tool_results", "audit_request_ids"):
        if key not in session:
            return fail(f"missing {key} in session json: {session}")

    if session.get("status") != "finished":
        return fail(f"unexpected session status: {session}")
    if task_text not in str(session.get("task_summary")):
        return fail(f"session task_summary did not include task text: {session}")
    if not isinstance(session.get("steps"), list) or not session["steps"]:
        return fail(f"session has no steps: {session}")
    if not isinstance(session.get("tool_results"), list) or not session["tool_results"]:
        return fail(f"session has no tool_results: {session}")
    if not isinstance(session.get("audit_request_ids"), list) or not session["audit_request_ids"]:
        return fail(f"session has no audit_request_ids: {session}")
    pass_step(f"session json recorded at {session_path}")

    for filename in OUTBOX_FILES.values():
        path = OUTBOX / filename
        if not path.exists():
            return fail(f"missing outbox artifact: {path}")
        text = path.read_text(encoding="utf-8", errors="replace")
        if task_text not in text:
            return fail(f"artifact missing task text: {path}")
    pass_step("github_outbox artifacts were generated")

    output = result["results"][0]["result"]
    if output.get("git_commit") or output.get("git_push") or output.get("github_create_pr"):
        return fail(f"forbidden mutation attempted: {output}")
    pass_step("no GitHub API, commit, or push was attempted")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
