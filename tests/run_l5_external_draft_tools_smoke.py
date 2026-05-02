from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.tools.external_draft_tools import GITHUB_DRAFT_FILES
from core.tools.tool_call import ToolCallExecutor
from core.tools.tool_registry import ToolRegistry


PREFIX = "[l5-external-draft-tools-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def observation(result: Dict[str, Any]) -> Dict[str, Any]:
    output = result.get("output") if isinstance(result.get("output"), dict) else {}
    return output.get("observation") if isinstance(output.get("observation"), dict) else {}


def main() -> int:
    registry = ToolRegistry(workspace_dir=str(REPO_ROOT))
    executor = ToolCallExecutor(registry)

    schemas = registry.list_tool_schemas()
    schema_names = {item.get("name") for item in schemas.get("schemas", []) if isinstance(item, dict)}
    if not {"web_search_draft", "github_draft_bundle"}.issubset(schema_names):
        return fail(f"missing external draft schemas: {schemas}")
    pass_step("registry exposes external draft tool schemas")

    source = (REPO_ROOT / "core" / "tools" / "external_draft_tools.py").read_text(encoding="utf-8", errors="replace")
    forbidden_network_markers = ("requests", "urllib", "http.client", "socket", "aiohttp")
    leaked_network = [item for item in forbidden_network_markers if item in source]
    if leaked_network:
        return fail(f"web_search_draft source contains network marker(s): {leaked_network}")

    web_result = executor.execute_decision(
        {
            "type": "tool_call",
            "tool": "web_search_draft",
            "args": {
                "query": "local AI agent tool calling",
                "max_results": 3,
            },
        },
        source="external_draft_smoke",
    )
    web_observation = observation(web_result)
    if web_result.get("ok") is not True or web_result.get("status") != "success":
        return fail(f"web_search_draft failed: {web_result}")
    if web_observation.get("type") != "web_search_draft":
        return fail(f"web_search_draft missing observation: {web_result}")
    if web_observation.get("network_access") is not False or web_observation.get("draft_only") is not True:
        return fail(f"web_search_draft did not declare draft/no-network mode: {web_observation}")
    pass_step("web_search_draft returns draft observation with network_access=false")

    git_head = REPO_ROOT / ".git" / "HEAD"
    git_head_before = git_head.read_text(encoding="utf-8", errors="replace") if git_head.exists() else ""
    outbox = REPO_ROOT / "workspace" / "github_outbox"
    outbox.mkdir(parents=True, exist_ok=True)

    github_args = {
        "title": "Add L5 tool decision core",
        "summary": "Implemented bounded tool decision loop with policy checks.",
        "changes": [
            "Added tool_decision_policy.py",
            "Updated tool_call.py",
            "Added L5 smoke test",
        ],
        "validation": [
            "run_l4_tool_layer_smoke.py PASS",
            "run_l4_tool_decision_smoke.py PASS",
            "run_l5_tool_decision_core_smoke.py PASS",
        ],
    }
    github_result = executor.execute_decision(
        {
            "type": "tool_call",
            "tool": "github_draft_bundle",
            "args": github_args,
        },
        source="external_draft_smoke",
    )
    github_observation = observation(github_result)
    if github_result.get("ok") is not True or github_result.get("status") != "success":
        return fail(f"github_draft_bundle failed: {github_result}")
    files = github_observation.get("files") if isinstance(github_observation.get("files"), list) else []
    if files != list(GITHUB_DRAFT_FILES):
        return fail(f"github_draft_bundle observation listed wrong files: {github_observation}")
    missing = [path for path in GITHUB_DRAFT_FILES if not (REPO_ROOT / path).exists()]
    if missing:
        return fail(f"github_draft_bundle did not create expected files: {missing}")
    if github_observation.get("api_access") is not False or github_observation.get("draft_only") is not True:
        return fail(f"github_draft_bundle did not declare draft/no-api mode: {github_observation}")
    pass_step("github_draft_bundle creates the expected draft outbox files")

    git_head_after = git_head.read_text(encoding="utf-8", errors="replace") if git_head.exists() else ""
    if git_head_before != git_head_after:
        return fail(".git/HEAD changed during github_draft_bundle")
    forbidden_git_markers = ("subprocess", "os.system", "git push", "git merge", "git commit", "force-push")
    leaked_git = [item for item in forbidden_git_markers if item in source]
    if leaked_git:
        return fail(f"github_draft_bundle source contains git execution marker(s): {leaked_git}")
    pass_step("github_draft_bundle does not touch .git or run git-style commands")

    invalid_result = executor.execute_decision(
        {
            "type": "tool_call",
            "tool": "github_draft_bundle",
            "args": {
                "title": "Bad draft",
                "summary": "changes is not a list",
                "changes": "not-a-list",
            },
        },
        source="external_draft_smoke",
    )
    if invalid_result.get("ok") is not False or invalid_result.get("status") != "invalid_args":
        return fail(f"invalid github_draft_bundle args did not return validation error: {invalid_result}")
    pass_step("invalid github_draft_bundle args return validation error")

    unsafe_args = dict(github_args)
    unsafe_args["output_path"] = "../outside.md"
    denied_result = executor.execute_decision(
        {
            "type": "tool_call",
            "tool": "github_draft_bundle",
            "args": unsafe_args,
        },
        source="external_draft_smoke",
    )
    if denied_result.get("ok") is not False or denied_result.get("status") != "denied":
        return fail(f"unsafe github_draft_bundle path was not denied: {denied_result}")
    pass_step("unsafe github_draft_bundle output path is denied by policy")

    unknown_result = executor.execute_decision(
        {"type": "tool_call", "tool": "external_live_tool", "args": {}},
        source="external_draft_smoke",
    )
    if unknown_result.get("ok") is not False or unknown_result.get("status") != "invalid_tool":
        return fail(f"unknown external tool did not return blocked/error observation: {unknown_result}")
    pass_step("unknown external tool returns normal blocked/error observation")

    scheduler_path = REPO_ROOT / "core" / "tasks" / "scheduler.py"
    scheduler_text = scheduler_path.read_text(encoding="utf-8", errors="replace")
    forbidden_scheduler_refs: List[str] = [
        "tool_decision",
        "tool_executor",
        "external_draft_tools",
        "filesystem_tools",
    ]
    leaked_scheduler = [item for item in forbidden_scheduler_refs if item in scheduler_text]
    if leaked_scheduler:
        return fail(f"scheduler leaked tool layer details: {leaked_scheduler}")
    pass_step("scheduler remains unaware of external draft tool details")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
