from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.tools.commit_message_generator import (
    generate_commit_message,
    generate_commit_message_to_outbox,
)
from core.tools.readonly_tools import git_diff, git_status


PREFIX = "[commit-message-generator-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def changed_files_from_status(status_text: str) -> list[str]:
    files = []
    for line in status_text.splitlines():
        if len(line) > 3:
            files.append(line[3:].strip())
    return files


def main() -> int:
    print(f"{PREFIX} START")

    diff_result = git_diff(
        repo_root=REPO_ROOT,
        task_id="task_commit_message",
        trace_id="trace_commit_message_diff",
    )
    if not diff_result.get("ok"):
        return fail(f"git_diff failed: {diff_result}")

    status_result = git_status(
        repo_root=REPO_ROOT,
        task_id="task_commit_message",
        trace_id="trace_commit_message_status",
    )
    if not status_result.get("ok"):
        return fail(f"git_status failed: {status_result}")

    changed_files = changed_files_from_status(str(status_result.get("stdout") or ""))
    summary = "Fix tool policy preflight handling"

    generated = generate_commit_message(
        diff_text=str(diff_result.get("stdout") or ""),
        summary=summary,
        changed_files=changed_files,
        task_id="task_commit_message",
        trace_id="trace_commit_message_generate",
    )
    if not generated.get("ok"):
        return fail(f"commit message generation failed: {generated}")
    if generated.get("tool_class") != "generate_only":
        return fail(f"generator tool_class mismatch: {generated}")
    if generated.get("side_effect_level") != "none":
        return fail(f"generator side_effect_level mismatch: {generated}")
    if generated.get("changed_files") != []:
        return fail(f"generator changed files directly: {generated}")
    if generated.get("output_schema") != "commit_message.v1":
        return fail(f"commit message schema mismatch: {generated}")
    output = generated.get("output")
    if not isinstance(output, dict):
        return fail(f"commit message output is not structured: {generated}")
    if set(output.keys()) != {"title", "body"}:
        return fail(f"commit message output keys mismatch: {output}")
    if generated.get("title") != output.get("title") or generated.get("body") != output.get("body"):
        return fail(f"top-level schema fields do not mirror output: {generated}")
    message = str(generated.get("message") or "")
    if output.get("title") != "Fix tool policy preflight handling":
        return fail(f"commit message title mismatch: {output}")
    if not message.startswith("Fix tool policy preflight handling"):
        return fail(f"commit message title mismatch: {message}")
    if "- Touch " not in str(output.get("body") or ""):
        return fail(f"commit message body did not include changed-file bullet: {output}")
    pass_step("generated commit message uses stable title/body schema")

    trace = generated.get("trace", {})
    if trace.get("tool_class") != "generate_only" or trace.get("side_effect_level") != "none":
        return fail(f"generator trace mismatch: {trace}")
    if trace.get("origin") != "commit_message_generator":
        return fail(f"generator trace origin mismatch: {trace}")
    pass_step("generator trace is generate_only with origin and no side effect")

    pipeline = generate_commit_message_to_outbox(
        diff_text=str(diff_result.get("stdout") or ""),
        summary=summary,
        changed_files=changed_files,
        workspace_root=REPO_ROOT,
        task_id="task_commit_message",
        trace_id="trace_commit_message_pipeline",
    )
    if not pipeline.get("ok"):
        return fail(f"commit message outbox pipeline failed: {pipeline}")

    outbox = pipeline.get("outbox_result", {})
    output_path = Path(outbox.get("output_path", ""))
    expected_path = REPO_ROOT / "workspace/github_outbox/commit_message.txt"
    if output_path != expected_path:
        return fail(f"unexpected commit message output path: {output_path}")
    if output_path.read_text(encoding="utf-8") != pipeline.get("message"):
        return fail("commit message outbox content mismatch")
    if pipeline.get("output_schema") != "commit_message.v1":
        return fail(f"pipeline schema mismatch: {pipeline}")
    if pipeline.get("title") != generated.get("title") or pipeline.get("body") != generated.get("body"):
        return fail(f"pipeline did not preserve structured output: {pipeline}")
    pass_step("commit message is written only through github_outbox allowlist")

    if pipeline.get("git_commit") or pipeline.get("git_push") or pipeline.get("github_create_pr"):
        return fail(f"pipeline attempted git/GitHub mutation: {pipeline}")
    if outbox.get("git_commit") or outbox.get("git_push") or outbox.get("github_create_pr"):
        return fail(f"outbox attempted git/GitHub mutation: {outbox}")
    pass_step("commit message pipeline does not commit, push, or create PR")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
