from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from core.tools.tool_schema import ToolRequest, ToolResult


AUDIT_LOG_DIR = "audit_logs"
AUDIT_LOG_FILE = "tool_audit.jsonl"


def resolve_audit_log_path(workspace_dir: str = "workspace") -> Path:
    workspace_path = Path(workspace_dir).resolve(strict=False)
    if workspace_path.name != "workspace":
        workspace_path = workspace_path / "workspace"
    return workspace_path / AUDIT_LOG_DIR / AUDIT_LOG_FILE


def write_tool_audit_log(
    *,
    request: ToolRequest,
    result: ToolResult,
    workspace_dir: str = "workspace",
) -> Path:
    path = resolve_audit_log_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": result.request_id or request.request_id,
        "source": request.source,
        "tool": result.tool or request.tool,
        "risk_level": request.risk_level,
        "side_effect_level": result.side_effect_level,
        "ok": bool(result.ok),
        "input_summary": summarize_payload(request.input),
        "output_summary": summarize_payload(result.output),
        "error": summarize_error(result.error),
    }

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    return path


def summarize_error(error: Any) -> Any:
    if error is None:
        return None
    return _summarize(error, depth=0)


def summarize_payload(payload: Any) -> Any:
    return _summarize(payload, depth=0)


def _summarize(value: Any, *, depth: int) -> Any:
    if depth >= 4:
        return _type_summary(value)

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        return _summarize_string(value)

    if is_dataclass(value):
        return _summarize(asdict(value), depth=depth + 1)

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return _summarize_dict(value, depth=depth)

    if isinstance(value, (list, tuple, set)):
        items = list(value)
        summarized = [_summarize(item, depth=depth + 1) for item in items[:8]]
        if len(items) > 8:
            summarized.append({"truncated_items": len(items) - 8})
        return summarized

    return _summarize_string(str(value))


def _summarize_dict(payload: Dict[Any, Any], *, depth: int) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    items = list(payload.items())
    for key, value in items[:12]:
        key_text = str(key)
        if _looks_like_large_content_key(key_text):
            summary[key_text] = _type_summary(value)
        else:
            summary[key_text] = _summarize(value, depth=depth + 1)

    if len(items) > 12:
        summary["truncated_keys"] = len(items) - 12

    return summary


def _summarize_string(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if len(normalized) <= 200:
        return normalized
    return f"{normalized[:200]}... <truncated len={len(normalized)}>"


def _type_summary(value: Any) -> Dict[str, Any]:
    if isinstance(value, str):
        return {"type": "str", "length": len(value)}
    if isinstance(value, dict):
        return {"type": "dict", "keys": len(value)}
    if isinstance(value, (list, tuple, set)):
        return {"type": type(value).__name__, "items": len(value)}
    return {"type": type(value).__name__}


def _looks_like_large_content_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in {
        "content",
        "file_content",
        "raw_content",
        "text_content",
        "body",
        "stdout",
        "stderr",
    }
