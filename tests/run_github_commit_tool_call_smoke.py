from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.agent.agent_loop import AgentLoop
from core.tools.tool_registry import ToolRegistry


PREFIX = "[github-commit-tool-call-smoke]"
TEST_RUNS = REPO_ROOT / "workspace" / "test_runs"


class GitHubCommitPlanner:
    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path

    def plan(self, **_: Any) -> Dict[str, Any]:
        return {
            "ok": True,
            "intent": "tool_call",
            "tool_call": {
                "tool": "github_commit",
                "args": {
                    "repo_path": str(self.repo_path),
                    "message": "test: add generated file",
                    "files": [
                        {
                            "path": "generated/hello.txt",
                            "content": "hello from github_commit tool\n",
                        }
                    ],
                },
            },
        }


class BlockedRepoPlanner:
    def plan(self, **_: Any) -> Dict[str, Any]:
        return {
            "ok": True,
            "intent": "tool_call",
            "tool_call": {
                "tool": "github_commit",
                "args": {
                    "repo_path": str(REPO_ROOT.parent),
                    "message": "test: should be blocked",
                    "files": [
                        {
                            "path": "blocked.txt",
                            "content": "nope\n",
                        }
                    ],
                },
            },
        }


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def run_git(repo_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo_path),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        shell=False,
    )


def main() -> int:
    TEST_RUNS.mkdir(parents=True, exist_ok=True)
    repo_path = TEST_RUNS / f"github_commit_tool_call_{int(time.time() * 1000)}"
    if repo_path.exists():
        shutil.rmtree(repo_path)
    repo_path.mkdir(parents=True)

    init_result = run_git(repo_path, "init")
    if init_result.returncode != 0:
        return fail(f"git init failed: {init_result.stderr}")

    registry = ToolRegistry(workspace_dir=str(REPO_ROOT))
    if not registry.has_tool("github_commit"):
        return fail("github_commit tool is not registered")
    pass_step("github_commit is registered")

    loop = AgentLoop(
        planner=GitHubCommitPlanner(repo_path),
        tool_registry=registry,
        workspace_dir=str(REPO_ROOT),
    )
    result = loop.run("generate a file and commit it to repo")
    if not result.get("ok"):
        return fail(f"agent loop failed: {result}")
    pass_step("agent loop executed github_commit tool_call")

    generated_file = repo_path / "generated" / "hello.txt"
    if not generated_file.exists():
        return fail(f"generated file missing: {generated_file}")
    pass_step("generated file was written inside repo")

    log_result = run_git(repo_path, "log", "--oneline", "-1")
    if log_result.returncode != 0:
        return fail(f"git log failed: {log_result.stderr}")
    if "test: add generated file" not in log_result.stdout:
        return fail(f"git log does not contain commit message: {log_result.stdout}")
    pass_step("git log contains the generated commit")

    execution = result.get("execution")
    if not isinstance(execution, dict):
        return fail(f"execution missing: {result}")

    execution_trace = execution.get("execution_trace")
    if not isinstance(execution_trace, list) or not execution_trace:
        return fail(f"execution_trace missing tool_call: {execution}")
    if execution_trace[0].get("event_type") != "tool_call" or execution_trace[0].get("tool") != "github_commit":
        return fail(f"execution_trace does not record github_commit tool_call: {execution_trace}")
    pass_step("execution_trace records github_commit tool_call")

    last_result = execution.get("last_result")
    output = last_result.get("output") if isinstance(last_result, dict) else {}
    commit_hash = output.get("commit_hash") if isinstance(output, dict) else ""
    if not isinstance(commit_hash, str) or len(commit_hash) < 7:
        return fail(f"commit hash missing from tool output: {last_result}")
    if output.get("git_push") or output.get("github_create_pr"):
        return fail(f"tool attempted forbidden remote operation: {output}")
    pass_step("tool output returned commit hash without push or PR")

    blocked_loop = AgentLoop(
        planner=BlockedRepoPlanner(),
        tool_registry=registry,
        workspace_dir=str(REPO_ROOT),
    )
    blocked_result = blocked_loop.run("attempt commit outside allowed repo root")
    blocked_execution = blocked_result.get("execution") if isinstance(blocked_result, dict) else {}
    blocked_last = blocked_execution.get("last_result") if isinstance(blocked_execution, dict) else {}
    if blocked_last.get("status") != "blocked":
        return fail(f"outside repo_path did not return blocked: {blocked_result}")
    pass_step("repo_path outside allowed directory returns blocked")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
