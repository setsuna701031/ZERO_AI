from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.tools.commit_message_generator import generate_commit_message
from core.tools.pr_description_generator import generate_pr_description_to_outbox
from core.tools.readonly_tools import git_diff, git_status


PREFIX = "[github-outbox-pipeline-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def analyze_changes(diff_text: str, status_text: str) -> dict:
    files = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                files.append(parts[3].removeprefix("b/"))
    if not files:
        for line in status_text.splitlines():
            if len(line) > 3:
                files.append(line[3:].strip())

    return {
        "files": files,
        "summary": "Analyzes the current repository changes and writes a PR description artifact.",
        "risk": "Low: read-only git inputs feed an allowlisted github_outbox workspace artifact.",
    }


def main() -> int:
    print(f"{PREFIX} START")

    user_input = "幫我分析目前變更並產生 PR 描述"
    print(f"{PREFIX} input: {user_input}")

    diff_result = git_diff(
        repo_root=REPO_ROOT,
        task_id="task_outbox_pipeline",
        trace_id="trace_pipeline_git_diff",
    )
    if not diff_result.get("ok"):
        return fail(f"real git_diff failed: {diff_result}")
    pass_step("real git_diff produced read-only input")

    status_result = git_status(
        repo_root=REPO_ROOT,
        task_id="task_outbox_pipeline",
        trace_id="trace_pipeline_git_status",
    )
    if not status_result.get("ok"):
        return fail(f"real git_status failed: {status_result}")
    pass_step("real git_status produced read-only input")

    analysis = analyze_changes(
        str(diff_result.get("stdout") or ""),
        str(status_result.get("stdout") or ""),
    )
    if not analysis.get("files"):
        return fail(f"change analysis produced no files: {analysis}")
    pass_step("analyzed real read-only git input")

    commit_message = generate_commit_message(
        diff_text=str(diff_result.get("stdout") or ""),
        summary=str(analysis.get("summary") or ""),
        changed_files=analysis.get("files"),
        task_id="task_outbox_pipeline",
        trace_id="trace_outbox_pipeline_commit_message",
    )
    if not commit_message.get("ok"):
        return fail(f"commit message generation failed: {commit_message}")
    if commit_message.get("output_schema") != "commit_message.v1":
        return fail(f"commit message schema mismatch: {commit_message}")
    pass_step("generated structured commit message")

    result = generate_pr_description_to_outbox(
        analysis=analysis,
        commit_message=commit_message,
        workspace_root=REPO_ROOT,
        task_id="task_outbox_pipeline",
        trace_id="trace_outbox_pipeline_pr_description",
    )
    if not result.get("ok"):
        return fail(f"PR description outbox pipeline failed: {result}")
    if result.get("output_schema") != "pr_description.v1":
        return fail(f"PR description schema mismatch: {result}")
    pass_step("generated structured PR description and wrote through github_outbox")

    outbox_result = result.get("outbox_result", {})
    output_path = Path(outbox_result.get("output_path", ""))
    expected_path = REPO_ROOT / "workspace/github_outbox/pr_description.md"
    if output_path != expected_path:
        return fail(f"unexpected output path: {output_path}")
    if output_path.read_text(encoding="utf-8") != result.get("message"):
        return fail("outbox PR description content mismatch")
    pass_step("outbox wrote only the allowlisted PR description file")

    trace = outbox_result.get("trace", {})
    if trace.get("tool_name") != "github_outbox":
        return fail(f"trace missing tool_name: {trace}")
    if trace.get("tool_class") != "workspace_write":
        return fail(f"trace missing tool_class: {trace}")
    if trace.get("side_effect_level") != "workspace_write":
        return fail(f"trace missing side_effect_level: {trace}")
    if Path(trace.get("output_path", "")) != expected_path:
        return fail(f"trace output path mismatch: {trace}")
    pass_step("trace records outbox workspace write")

    generation_trace = result.get("generation_result", {}).get("trace", {})
    if generation_trace.get("origin") != "pr_description_generator":
        return fail(f"PR generation trace origin mismatch: {generation_trace}")
    pass_step("PR generation trace records origin")

    if result.get("git_commit") or result.get("git_push") or result.get("github_create_pr"):
        return fail(f"pipeline attempted GitHub mutation: {result}")
    pass_step("pipeline does not commit, push, or create PR")

    for readonly_result, label in ((diff_result, "git_diff"), (status_result, "git_status")):
        if readonly_result.get("changed_files") != []:
            return fail(f"{label} changed files: {readonly_result}")
        if readonly_result.get("git_commit") or readonly_result.get("git_push"):
            return fail(f"{label} reported git mutation: {readonly_result}")
    pass_step("real read-only inputs did not mutate repository")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
