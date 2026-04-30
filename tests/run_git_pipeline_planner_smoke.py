from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.planning.planner import Planner
from core.tools.tool_registry import ToolRegistry


PREFIX = "[git-pipeline-planner-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def main() -> int:
    print(f"{PREFIX} START")

    planner = Planner()
    plan = planner.plan(
        user_input="analyze git diff -> generate commit message -> PR -> outbox",
        context={"repo_root": str(REPO_ROOT)},
    )

    if plan.get("ok") is not True:
        return fail(f"planner failed: {plan}")
    if plan.get("meta", {}).get("fallback_used") is not False:
        return fail(f"planner should not use fallback: {plan}")
    if plan.get("semantic_type") != "git_pipeline_task":
        return fail(f"semantic_type mismatch: {plan}")
    if plan.get("execution_route") != "git_pipeline_path":
        return fail(f"execution_route mismatch: {plan}")
    steps = plan.get("steps")
    if not isinstance(steps, list) or len(steps) != 1:
        return fail(f"expected one tool step: {plan}")
    step = steps[0]
    if step.get("type") != "tool" or step.get("tool_name") != "git_pipeline":
        return fail(f"expected git_pipeline tool step: {step}")
    pass_step("planner routes git pipeline intent to tool step")

    registry = ToolRegistry(workspace_dir=str(REPO_ROOT))
    if not registry.has_tool("git_pipeline"):
        return fail("ToolRegistry did not register git_pipeline")
    pass_step("tool registry resolves git_pipeline")

    result = registry.execute_tool(
        "git_pipeline",
        {
            "repo_root": str(REPO_ROOT),
            "task_id": "task_git_pipeline_planner_smoke",
            "trace_id": "trace_git_pipeline_planner_smoke",
        },
    )
    if result.get("ok") is not True:
        return fail(f"git_pipeline registry execution failed: {result}")

    output = result.get("output")
    if not isinstance(output, dict) or output.get("ok") is not True:
        return fail(f"git_pipeline output failed: {result}")
    if output.get("git_commit") or output.get("git_push") or output.get("github_create_pr"):
        return fail(f"git_pipeline attempted mutation: {output}")

    artifacts = output.get("artifacts")
    if not isinstance(artifacts, dict):
        return fail(f"missing artifacts map: {output}")

    expected_commit = REPO_ROOT / "workspace/github_outbox/commit_message.txt"
    expected_pr = REPO_ROOT / "workspace/github_outbox/pr_description.md"
    if Path(str(artifacts.get("commit_message") or "")) != expected_commit:
        return fail(f"commit artifact mismatch: {artifacts}")
    if Path(str(artifacts.get("pr_description") or "")) != expected_pr:
        return fail(f"PR artifact mismatch: {artifacts}")
    if not expected_commit.exists() or not expected_pr.exists():
        return fail(f"outbox artifacts were not written: {artifacts}")
    pass_step("git_pipeline writes commit message and PR description to github_outbox only")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
