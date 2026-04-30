from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.tools.github_outbox import OUTBOX_ARTIFACTS, write_github_outbox_artifact


PREFIX = "[github-outbox-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def main() -> int:
    print(f"{PREFIX} START")

    root = REPO_ROOT

    expected_files = {
        "commit_message": root / "workspace/github_outbox/commit_message.txt",
        "pr_description": root / "workspace/github_outbox/pr_description.md",
        "devlog": root / "workspace/github_outbox/devlog.md",
        "review_report": root / "workspace/github_outbox/review_report.md",
    }
    for artifact, expected_path in expected_files.items():
        result = write_github_outbox_artifact(
            artifact,
            f"{artifact} content",
            workspace_root=root,
            task_id="task_outbox",
            trace_id=f"trace_{artifact}",
        )
        if not result.get("ok"):
            return fail(f"{artifact} write failed: {result}")
        if Path(result.get("output_path", "")) != expected_path:
            return fail(f"{artifact} output path mismatch: {result}")
        if expected_path.read_text(encoding="utf-8") != f"{artifact} content":
            return fail(f"{artifact} content mismatch")
        pass_step(f"writes allowlisted {artifact} artifact")

        trace = result.get("trace", {})
        if trace.get("tool_name") != "github_outbox":
            return fail(f"{artifact} trace missing tool_name: {trace}")
        if trace.get("tool_class") != "workspace_write":
            return fail(f"{artifact} trace missing tool_class: {trace}")
        if trace.get("side_effect_level") != "workspace_write":
            return fail(f"{artifact} trace missing side_effect_level: {trace}")
        if Path(trace.get("output_path", "")) != expected_path:
            return fail(f"{artifact} trace output_path mismatch: {trace}")
        if trace.get("policy_decision", {}).get("ok") is not True:
            return fail(f"{artifact} trace policy decision missing: {trace}")
        pass_step(f"trace records {artifact} workspace write")

        if result.get("git_commit") or result.get("git_push") or result.get("github_create_pr"):
            return fail(f"{artifact} attempted GitHub mutation: {result}")
        pass_step(f"{artifact} does not commit, push, or create PR")

    unknown = write_github_outbox_artifact(
        "secret",
        "nope",
        workspace_root=root,
        task_id="task_outbox",
        trace_id="trace_secret",
    )
    if unknown.get("ok"):
        return fail(f"unknown artifact was accepted: {unknown}")
    if unknown.get("changed_files"):
        return fail(f"unknown artifact changed files: {unknown}")
    pass_step("rejects unknown outbox artifact names")

    blocked_names = [
        "deploy.ps1",
        "../secret.txt",
        "workspace/github_outbox/pr.md",
    ]
    allowed_values = set(OUTBOX_ARTIFACTS.values())
    for name in blocked_names:
        if name in allowed_values:
            return fail(f"blocked name accidentally allowlisted: {name}")
    pass_step("outbox allowlist excludes scripts and traversal targets")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
