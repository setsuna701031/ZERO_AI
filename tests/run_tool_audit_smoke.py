from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.tools.tool_audit_log import resolve_audit_log_path
from core.tools.tool_registry import ToolRegistry
from core.tools.tool_schema import ToolRequest


PREFIX = "[tool-audit-smoke]"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def main() -> int:
    audit_path = resolve_audit_log_path(str(REPO_ROOT))
    before_count = len(read_records(audit_path))

    request = ToolRequest(
        tool="github_outbox",
        input={"task": "audit test"},
        source="audit_smoke",
    )
    result = ToolRegistry(workspace_dir=str(REPO_ROOT)).execute_tool_request(request)

    if result.ok is not True:
        return fail(f"ToolResult not ok: {result}")
    if not result.request_id:
        return fail(f"missing result request_id: {result}")
    if not audit_path.exists():
        return fail(f"audit log was not created: {audit_path}")

    records = read_records(audit_path)
    if len(records) != before_count + 1:
        return fail(f"expected one new audit row, before={before_count}, after={len(records)}")

    record = records[-1]
    if record.get("tool") != "github_outbox":
        return fail(f"unexpected tool in audit record: {record}")
    if record.get("source") != "audit_smoke":
        return fail(f"unexpected source in audit record: {record}")
    if record.get("ok") is not True:
        return fail(f"unexpected ok in audit record: {record}")
    if not record.get("side_effect_level"):
        return fail(f"missing side_effect_level in audit record: {record}")
    if not record.get("request_id"):
        return fail(f"missing request_id in audit record: {record}")
    if record.get("request_id") != result.request_id:
        return fail(f"audit request_id does not match result: {record} vs {result.request_id}")

    print(f"{PREFIX} PASS: audit log appended at {audit_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
