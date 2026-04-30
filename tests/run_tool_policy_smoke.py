from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.tools.tool_policy import (
    build_tool_trace_event,
    evaluate_tool_policy,
    is_executable_sensitive_output,
    preflight_check,
    resolve_allowed_outbox_path,
)


PREFIX = "[tool-policy-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def assert_policy(
    *,
    tool_class: str,
    side_effect_level: str,
    output_path: str = "",
    expected_ok: bool,
    expected_reason: str,
    label: str,
) -> int:
    decision = evaluate_tool_policy(
        tool_class=tool_class,
        actual_side_effect_level=side_effect_level,
        output_path=output_path,
        workspace_root=REPO_ROOT,
    )
    if decision.get("ok") is not expected_ok:
        return fail(f"{label}: expected ok={expected_ok}, got {decision}")
    if decision.get("reason") != expected_reason:
        return fail(f"{label}: expected reason={expected_reason}, got {decision}")
    pass_step(label)
    return 0


def main() -> int:
    print(f"{PREFIX} START")

    checks = [
        assert_policy(
            tool_class="read_only",
            side_effect_level="read_only",
            expected_ok=True,
            expected_reason="tool_capability_matches_side_effect",
            label="read_only declaration matches read_only side effect",
        ),
        assert_policy(
            tool_class="generate_only",
            side_effect_level="none",
            expected_ok=True,
            expected_reason="tool_capability_matches_side_effect",
            label="generate_only declaration matches no side effect",
        ),
        assert_policy(
            tool_class="generate_only",
            side_effect_level="workspace_write",
            output_path="workspace/github_outbox/pr_description.md",
            expected_ok=False,
            expected_reason="side_effect_mismatch",
            label="generate_only cannot secretly write workspace files",
        ),
        assert_policy(
            tool_class="workspace_write",
            side_effect_level="workspace_write",
            output_path="workspace/github_outbox/pr_description.md",
            expected_ok=True,
            expected_reason="workspace_write_allowed_outbox_artifact",
            label="workspace_write can target allowlisted outbox artifact",
        ),
        assert_policy(
            tool_class="workspace_write",
            side_effect_level="workspace_write",
            output_path="workspace/github_outbox/../secret.txt",
            expected_ok=False,
            expected_reason="output_path_not_allowlisted",
            label="outbox path traversal is rejected after normalization",
        ),
        assert_policy(
            tool_class="workspace_write",
            side_effect_level="workspace_write",
            output_path="workspace/github_outbox/run_this.ps1",
            expected_ok=False,
            expected_reason="output_path_not_allowlisted",
            label="workspace_write only allows fixed outbox artifact names",
        ),
        assert_policy(
            tool_class="external_write",
            side_effect_level="external_write",
            expected_ok=False,
            expected_reason="external_write_disabled",
            label="external_write is declared but disabled",
        ),
    ]
    if any(check != 0 for check in checks):
        return 1

    allowed = resolve_allowed_outbox_path(
        "workspace/github_outbox/commit_message.txt",
        workspace_root=REPO_ROOT,
    )
    if allowed is None or not str(allowed).endswith("workspace\\github_outbox\\commit_message.txt"):
        return fail(f"allowed outbox path did not resolve as expected: {allowed}")
    pass_step("allowed outbox path is normalized to a concrete path")

    if resolve_allowed_outbox_path(
        "workspace/github_outbox/../../app.py",
        workspace_root=REPO_ROOT,
    ) is not None:
        return fail("escaped outbox path was accepted")
    pass_step("escaped outbox path is rejected")

    sensitive_paths = [
        ".github/workflows/deploy.yml",
        "workspace/github_outbox/deploy.sh",
        "workspace/github_outbox/deploy.ps1",
        "Dockerfile",
        ".gitignore",
    ]
    for path in sensitive_paths:
        if not is_executable_sensitive_output(path):
            return fail(f"sensitive output path was not detected: {path}")
    pass_step("generate_only sensitive output patterns are detected")

    sensitive_decision = evaluate_tool_policy(
        tool_class="generate_only",
        actual_side_effect_level="none",
        output_path=".github/workflows/deploy.yml",
        workspace_root=REPO_ROOT,
    )
    if sensitive_decision.get("ok") is not False:
        return fail(f"generate_only sensitive target was accepted: {sensitive_decision}")
    if sensitive_decision.get("reason") != "generate_only_sensitive_output_target":
        return fail(f"unexpected sensitive target reason: {sensitive_decision}")
    pass_step("generate_only cannot target executable-sensitive filenames")

    policy_decision = evaluate_tool_policy(
        tool_class="workspace_write",
        actual_side_effect_level="workspace_write",
        output_path="workspace/github_outbox/devlog.md",
        workspace_root=REPO_ROOT,
    )
    trace = build_tool_trace_event(
        trace_id="trace_fixed",
        task_id="task_fixed",
        tool_name="github_outbox_writer",
        tool_class="workspace_write",
        input_summary="write generated devlog artifact",
        output_path=policy_decision.get("output_path", ""),
        output_summary="devlog artifact",
        side_effect_level="workspace_write",
        policy_decision=policy_decision,
        executor_approved=True,
        status="success",
        tool_input_full={"output_path": "workspace/github_outbox/devlog.md"},
    )
    required_trace_keys = {
        "trace_id",
        "task_id",
        "timestamp",
        "tool_name",
        "tool_class",
        "input_summary",
        "output_path",
        "output_summary",
        "side_effect_level",
        "policy_decision",
        "executor_approved",
        "status",
        "error",
        "tool_input_full",
    }
    missing = required_trace_keys - set(trace.keys())
    if missing:
        return fail(f"trace event missing replay keys: {sorted(missing)}")
    if trace.get("trace_id") != "trace_fixed" or trace.get("task_id") != "task_fixed":
        return fail(f"trace replay ids not preserved: {trace}")
    if trace.get("policy_decision", {}).get("ok") is not True:
        return fail(f"trace policy decision not embedded: {trace}")
    pass_step("tool trace contains replay-ready metadata")

    preflight_cases = [
        (
            {"tool_name": "github_issue_reader", "action": "read"},
            "read_only",
            "preflight_read_only_action",
            "preflight detects read-only tool calls",
        ),
        (
            {
                "tool_name": "github_outbox_writer",
                "action": "write_file",
                "output_path": "workspace/github_outbox/devlog.md",
            },
            "workspace_write",
            "preflight_workspace_write_action",
            "preflight detects workspace write tool calls",
        ),
        (
            {"tool_name": "github", "action": "create_pr"},
            "external_write",
            "preflight_external_write_action",
            "preflight detects external write tool calls",
        ),
        (
            {"tool_name": "commit_message_generator", "action": "generate"},
            "none",
            "preflight_no_side_effect_detected",
            "preflight detects generate-only tool calls as no side effect",
        ),
    ]
    for tool_call, expected_level, expected_reason, label in preflight_cases:
        preflight = preflight_check(tool_call)
        if preflight.get("expected_side_effect_level") != expected_level:
            return fail(f"{label}: unexpected level {preflight}")
        if preflight.get("reason") != expected_reason:
            return fail(f"{label}: unexpected reason {preflight}")
        if "executor_approved" in preflight or "approved" in preflight:
            return fail(f"{label}: preflight leaked approval fields {preflight}")
        pass_step(label)

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
