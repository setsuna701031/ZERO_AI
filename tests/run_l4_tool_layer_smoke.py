from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.tools.tool_call import ToolCallExecutor
from core.tools.tool_executor import ToolExecutor
from core.tools.tool_registry import ToolRegistry
from core.tools.tool_schema import ToolRequest, ToolResult, ToolSpec


PREFIX = "[l4-tool-layer-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def require_observation(result: ToolResult, expected_type: str) -> int:
    observation = result.output.get("observation") if isinstance(result.output, dict) else {}
    if not isinstance(observation, dict):
        return fail(f"missing observation: {result}")
    if observation.get("type") != expected_type:
        return fail(f"unexpected observation type, expected {expected_type}: {observation}")
    trace = result.output.get("trace") if isinstance(result.output, dict) else {}
    if not isinstance(trace, dict) or not trace.get("tool_call_id"):
        return fail(f"missing replay trace metadata: {result.output}")
    return 0


def main() -> int:
    registry = ToolRegistry(workspace_dir=str(REPO_ROOT))
    executor = ToolExecutor(registry)

    schemas = registry.list_tool_schemas()
    if schemas.get("ok") is not True:
        return fail(f"schema listing failed: {schemas}")
    schema_names = {item.get("name") for item in schemas.get("schemas", []) if isinstance(item, dict)}
    expected_names = {"read_file", "write_file", "list_dir"}
    if not expected_names.issubset(schema_names):
        return fail(f"missing L4 schemas: {schemas}")
    for name in expected_names:
        spec = registry.get_tool_schema(name)
        if not isinstance(spec, ToolSpec):
            return fail(f"schema lookup did not return ToolSpec for {name}: {spec}")
        if spec.scope != "workspace":
            return fail(f"schema has wrong scope for {name}: {spec}")
    pass_step("registry exposes L4 tool schemas")

    write_request = ToolRequest(
        tool="write_file",
        input={
            "path": "shared/l4_tool_layer/hello.txt",
            "content": "hello from l4\n",
            "allow_overwrite": True,
        },
        source="l4_smoke",
    )
    write_result = executor.execute(write_request)
    if not isinstance(write_result, ToolResult) or write_result.ok is not True:
        return fail(f"write_file failed: {write_result}")
    if require_observation(write_result, "file_write") != 0:
        return 1
    pass_step("executor can run write_file through registry")

    overwrite_blocked = executor.execute(
        ToolRequest(
            tool="write_file",
            input={
                "path": "shared/l4_tool_layer/hello.txt",
                "content": "overwrite should be blocked\n",
            },
            source="l4_smoke",
        )
    )
    if overwrite_blocked.ok is not False or overwrite_blocked.output.get("status") != "blocked":
        return fail(f"write_file overwrite was not blocked: {overwrite_blocked}")
    pass_step("write_file blocks overwrite without explicit permission")

    read_result = executor.execute(
        ToolRequest(
            tool="read_file",
            input={"path": "shared/l4_tool_layer/hello.txt"},
            source="l4_smoke",
        )
    )
    if read_result.ok is not True:
        return fail(f"read_file failed: {read_result}")
    observation = read_result.output.get("observation")
    if require_observation(read_result, "file_content") != 0:
        return 1
    if "hello from l4" not in str(observation.get("data", {}).get("content", "")):
        return fail(f"read_file observation missing content: {observation}")
    pass_step("executor can run read_file and return observation")

    list_result = executor.execute(
        ToolRequest(
            tool="list_dir",
            input={"path": "shared/l4_tool_layer"},
            source="l4_smoke",
        )
    )
    if list_result.ok is not True:
        return fail(f"list_dir failed: {list_result}")
    if require_observation(list_result, "directory_listing") != 0:
        return 1
    pass_step("executor can run list_dir and return observation")

    escape_result = executor.execute(
        ToolRequest(
            tool="read_file",
            input={"path": "../outside.txt"},
            source="l4_smoke",
        )
    )
    if escape_result.ok is not False or escape_result.output.get("status") != "blocked":
        return fail(f"path traversal was not blocked: {escape_result}")
    policy = escape_result.output.get("policy") if isinstance(escape_result.output, dict) else {}
    if policy.get("reason") != "l4_parent_traversal_blocked":
        return fail(f"unexpected path traversal policy reason: {escape_result.output}")
    pass_step("policy blocks paths outside workspace")

    missing_arg = executor.execute(ToolRequest(tool="read_file", input={}, source="l4_smoke"))
    if missing_arg.ok is not False or missing_arg.error != "missing_required_arg:path":
        return fail(f"schema did not block missing path: {missing_arg}")
    pass_step("schema validation blocks missing required args")

    loop_result = ToolCallExecutor(registry).execute(
        {
            "tool": "read_file",
            "args": {
                "path": "shared/l4_tool_layer/hello.txt",
            },
        },
        source="agent_loop_smoke",
    )
    if loop_result.get("ok") is not True:
        return fail(f"ToolCallExecutor did not route through L4 executor: {loop_result}")
    loop_observation = loop_result.get("output", {}).get("observation")
    if not isinstance(loop_observation, dict) or loop_observation.get("type") != "file_content":
        return fail(f"agent-facing result missing observation: {loop_result}")
    pass_step("agent-facing tool call receives normalized observation")

    scheduler_path = REPO_ROOT / "core" / "tasks" / "scheduler.py"
    scheduler_text = scheduler_path.read_text(encoding="utf-8", errors="replace")
    forbidden_scheduler_refs = (
        "ToolExecutor",
        "filesystem_tools",
        "get_tool_schema",
        "list_tool_schemas",
    )
    leaked = [item for item in forbidden_scheduler_refs if item in scheduler_text]
    if leaked:
        return fail(f"scheduler leaked L4 tool layer details: {leaked}")
    pass_step("scheduler remains separate from tool layer details")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
