from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.persona.runtime_bridge import PersonaRuntimeBridge


PREFIX = "[hybrid-demo-smoke]"
SUMMARY_PATH = REPO_ROOT / "workspace" / "shared" / "search_summary.txt"


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
    if SUMMARY_PATH.exists():
        SUMMARY_PATH.unlink()

    bridge = PersonaRuntimeBridge(workspace_dir=REPO_ROOT)
    display = bridge.submit_hybrid_demo()
    if display.get("runtime_status") != "done":
        return fail(f"hybrid demo did not finish as done: {display}")
    pass_step("hybrid demo completed")

    search_summary = str(display.get("search_results_summary") or "")
    if "Results found:" not in search_summary:
        return fail(f"search summary missing result count: {display}")
    if "Traceable local AI agents" not in search_summary:
        return fail(f"search summary missing mock result title: {search_summary}")
    pass_step("search has summarized results")

    if not SUMMARY_PATH.exists():
        return fail(f"summary file missing: {SUMMARY_PATH}")
    summary_text = SUMMARY_PATH.read_text(encoding="utf-8", errors="replace")
    if "Search results summary" not in summary_text or "Safety:" not in summary_text:
        return fail(f"summary file missing expected content: {summary_text}")
    pass_step("summary was written")

    tool_calls = display.get("tool_calls")
    if not isinstance(tool_calls, list):
        return fail(f"tool calls missing: {display}")
    tool_names = [item.get("tool") for item in tool_calls if isinstance(item, dict)]
    if tool_names[:3] != ["web_search", "file_write", "github_commit"]:
        return fail(f"tool call order is wrong: {tool_calls}")
    pass_step("display includes web_search, file_write, github_commit")

    timeline = display.get("timeline")
    if not isinstance(timeline, list):
        return fail(f"timeline missing: {display}")
    timeline_tools = {item.get("tool") for item in timeline if isinstance(item, dict)}
    for expected in ("web_search", "file_write", "github_commit"):
        if expected not in timeline_tools:
            return fail(f"timeline missing {expected}: {timeline}")
    pass_step("timeline includes all three tool calls")

    trace = display.get("trace")
    if not isinstance(trace, list):
        return fail(f"trace missing: {display}")
    trace_tools = [item.get("tool") for item in trace if isinstance(item, dict) and item.get("event_type") == "tool_call"]
    if trace_tools != ["web_search", "file_write", "github_commit"]:
        return fail(f"trace does not contain three ordered tool_call events: {trace}")
    pass_step("trace has three ordered tool_call events")

    github_call = next((item for item in tool_calls if isinstance(item, dict) and item.get("tool") == "github_commit"), {})
    if github_call.get("status") != "success":
        return fail(f"github_commit did not succeed: {tool_calls}")
    last_result = display.get("last_result") if isinstance(display.get("last_result"), dict) else {}
    output = last_result.get("output") if isinstance(last_result.get("output"), dict) else {}
    commit_hash = output.get("commit_hash") if isinstance(output, dict) else ""
    if not isinstance(commit_hash, str) or len(commit_hash) < 7:
        return fail(f"commit hash missing: {last_result}")
    if output.get("git_push") or output.get("github_create_pr"):
        return fail(f"forbidden remote operation attempted: {output}")
    pass_step("commit succeeded without push or PR")

    repo_path = REPO_ROOT / "workspace" / "hybrid_demo_repo"
    log_result = run_git(repo_path, "log", "--oneline", "-1")
    if log_result.returncode != 0:
        return fail(f"git log failed: {log_result.stderr}")
    if "demo: commit hybrid search summary" not in log_result.stdout:
        return fail(f"latest commit message mismatch: {log_result.stdout}")
    pass_step("local git log contains hybrid demo commit")

    compact_summary = str(display.get("compact_demo_summary") or "")
    compact_needles = (
        "Step 1: web_search",
        "Step 2: file_write",
        "Step 3: github_commit",
        "Result:",
        "local git commit created",
    )
    for needle in compact_needles:
        if needle not in compact_summary:
            return fail(f"compact summary missing {needle}: {compact_summary}")
    pass_step("compact summary contains fixed demo outcome lines")

    formatted = bridge.format_display_text()
    if not formatted.startswith("[COMPACT DEMO SUMMARY]"):
        return fail(f"compact summary is not the first display block: {formatted}")
    for needle in ("[SEARCH RESULTS SUMMARY]", "[TASK FLOW]", "web_search", "file_write", "github_commit"):
        if needle not in formatted:
            return fail(f"formatted UI text missing {needle}: {formatted}")
    pass_step("formatted UI text shows compact summary above detailed trace")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
