from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.tools.commit_message_generator import generate_commit_message
from core.tools.pr_description_generator import (
    generate_pr_description,
    generate_pr_description_to_outbox,
)


PREFIX = "[pr-description-generator-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def main() -> int:
    print(f"{PREFIX} START")

    analysis = {
        "files": ["core/tools/tool_policy.py", "core/tools/readonly_tools.py"],
        "summary": "Improve guarded tool policy and read-only inputs.",
        "risk": "Low: generated artifacts stay in github_outbox.",
    }
    commit_message = generate_commit_message(
        summary="Fix tool policy preflight handling",
        changed_files=analysis["files"],
        task_id="task_pr_description",
        trace_id="trace_pr_description_commit",
    )
    if not commit_message.get("ok"):
        return fail(f"commit message generation failed: {commit_message}")

    generated = generate_pr_description(
        analysis=analysis,
        commit_message=commit_message,
        task_id="task_pr_description",
        trace_id="trace_pr_description_generate",
    )
    if not generated.get("ok"):
        return fail(f"PR description generation failed: {generated}")
    if generated.get("tool_class") != "generate_only":
        return fail(f"PR generator tool_class mismatch: {generated}")
    if generated.get("side_effect_level") != "none":
        return fail(f"PR generator side_effect_level mismatch: {generated}")
    if generated.get("output_schema") != "pr_description.v1":
        return fail(f"PR schema mismatch: {generated}")
    output = generated.get("output")
    if not isinstance(output, dict) or set(output.keys()) != {"title", "body"}:
        return fail(f"PR output schema mismatch: {generated}")
    if "## Summary" not in str(output.get("body") or ""):
        return fail(f"PR body missing summary section: {output}")
    if generated.get("changed_files") != []:
        return fail(f"PR generator changed files directly: {generated}")
    pass_step("PR description uses stable title/body schema")

    trace = generated.get("trace", {})
    if trace.get("origin") != "pr_description_generator":
        return fail(f"PR trace origin mismatch: {trace}")
    if trace.get("tool_class") != "generate_only" or trace.get("side_effect_level") != "none":
        return fail(f"PR trace policy fields mismatch: {trace}")
    pass_step("PR generator trace is generate_only with origin")

    pipeline = generate_pr_description_to_outbox(
        analysis=analysis,
        commit_message=commit_message,
        workspace_root=REPO_ROOT,
        task_id="task_pr_description",
        trace_id="trace_pr_description_pipeline",
    )
    if not pipeline.get("ok"):
        return fail(f"PR outbox pipeline failed: {pipeline}")
    outbox = pipeline.get("outbox_result", {})
    expected_path = REPO_ROOT / "workspace/github_outbox/pr_description.md"
    output_path = Path(outbox.get("output_path", ""))
    if output_path != expected_path:
        return fail(f"unexpected PR output path: {output_path}")
    if output_path.read_text(encoding="utf-8") != pipeline.get("message"):
        return fail("PR outbox content mismatch")
    if pipeline.get("git_commit") or pipeline.get("git_push") or pipeline.get("github_create_pr"):
        return fail(f"PR pipeline attempted mutation: {pipeline}")
    pass_step("PR description writes only through github_outbox allowlist")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
