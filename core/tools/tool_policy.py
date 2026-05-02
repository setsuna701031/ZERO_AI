from __future__ import annotations

import fnmatch
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional


class ToolClass(str, Enum):
    READ_ONLY = "read_only"
    GENERATE_ONLY = "generate_only"
    WORKSPACE_WRITE = "workspace_write"
    EXTERNAL_WRITE = "external_write"


class SideEffectLevel(str, Enum):
    NONE = "none"
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    EXTERNAL_WRITE = "external_write"


ALLOWED_SIDE_EFFECT_BY_TOOL_CLASS = {
    ToolClass.READ_ONLY: SideEffectLevel.READ_ONLY,
    ToolClass.GENERATE_ONLY: SideEffectLevel.NONE,
    ToolClass.WORKSPACE_WRITE: SideEffectLevel.WORKSPACE_WRITE,
    ToolClass.EXTERNAL_WRITE: SideEffectLevel.EXTERNAL_WRITE,
}

ALLOWED_GITHUB_OUTBOX_PATHS = {
    "workspace/github_outbox/commit_message.txt",
    "workspace/github_outbox/pr_description.md",
    "workspace/github_outbox/devlog.md",
    "workspace/github_outbox/devlog_entry.md",
    "workspace/github_outbox/publish_plan.md",
    "workspace/github_outbox/review_report.md",
}

GITHUB_DRAFT_BUNDLE_FILES = {
    "workspace/github_outbox/commit_message.txt",
    "workspace/github_outbox/pr_description.md",
    "workspace/github_outbox/devlog_entry.md",
    "workspace/github_outbox/publish_plan.md",
}

EXECUTABLE_SENSITIVE_PATTERNS = (
    ".github/workflows/*",
    "*.ps1",
    "*.sh",
    "Dockerfile",
    ".gitignore",
)


@dataclass(frozen=True)
class ToolPolicyDecision:
    ok: bool
    reason: str
    tool_class: str
    side_effect_level: str
    output_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "tool_class": self.tool_class,
            "side_effect_level": self.side_effect_level,
            "output_path": self.output_path,
        }


def evaluate_tool_policy(
    *,
    tool_class: Any,
    actual_side_effect_level: Any,
    output_path: str = "",
    workspace_root: Any = ".",
) -> Dict[str, Any]:
    declared = _parse_tool_class(tool_class)
    actual = _parse_side_effect_level(actual_side_effect_level)

    if declared is None:
        return _decision(False, "unknown_tool_class", tool_class, actual_side_effect_level)

    if actual is None:
        return _decision(False, "unknown_side_effect_level", tool_class, actual_side_effect_level)

    expected = ALLOWED_SIDE_EFFECT_BY_TOOL_CLASS[declared]
    if actual != expected:
        return _decision(
            False,
            "side_effect_mismatch",
            declared.value,
            actual.value,
            output_path=output_path,
        )

    if declared == ToolClass.EXTERNAL_WRITE:
        return _decision(
            False,
            "external_write_disabled",
            declared.value,
            actual.value,
            output_path=output_path,
        )

    if declared == ToolClass.WORKSPACE_WRITE:
        resolved = resolve_allowed_outbox_path(output_path, workspace_root=workspace_root)
        if resolved is None:
            return _decision(
                False,
                "output_path_not_allowlisted",
                declared.value,
                actual.value,
                output_path=output_path,
            )
        return _decision(
            True,
            "workspace_write_allowed_outbox_artifact",
            declared.value,
            actual.value,
            output_path=str(resolved),
        )

    if declared == ToolClass.GENERATE_ONLY and is_executable_sensitive_output(output_path):
        return _decision(
            False,
            "generate_only_sensitive_output_target",
            declared.value,
            actual.value,
            output_path=output_path,
        )

    return _decision(
        True,
        "tool_capability_matches_side_effect",
        declared.value,
        actual.value,
        output_path=output_path,
    )


def preflight_check(tool_call: Any) -> Dict[str, str]:
    """
    Estimate a tool call's side effect level before execution.

    This is planning metadata only. It does not approve, execute, route, or
    mutate a tool call.
    """
    call = tool_call if isinstance(tool_call, dict) else {}
    action = str(call.get("action") or call.get("operation") or "").strip().lower()
    tool_name = str(call.get("tool_name") or call.get("tool") or "").strip().lower()
    output_path = str(call.get("output_path") or call.get("path") or "").strip()

    if _looks_like_external_write(action, tool_name):
        level = SideEffectLevel.EXTERNAL_WRITE
        reason = "preflight_external_write_action"
    elif _looks_like_workspace_write(action, output_path):
        level = SideEffectLevel.WORKSPACE_WRITE
        reason = "preflight_workspace_write_action"
    elif _looks_like_read(action, tool_name):
        level = SideEffectLevel.READ_ONLY
        reason = "preflight_read_only_action"
    else:
        level = SideEffectLevel.NONE
        reason = "preflight_no_side_effect_detected"

    return {
        "expected_side_effect_level": level.value,
        "reason": reason,
    }


def evaluate_l4_tool_request(
    *,
    tool_name: str,
    args: Dict[str, Any],
    tool_class: str,
    side_effect_level: str,
    scope: str,
) -> Dict[str, Any]:
    normalized_tool = str(tool_name or "").strip().lower()
    normalized_scope = str(scope or "").strip().lower()
    normalized_class = str(tool_class or "").strip().lower()
    normalized_side_effect = str(side_effect_level or "").strip().lower()
    payload = args if isinstance(args, dict) else {}

    if normalized_scope != "workspace":
        return _decision(False, "l4_scope_not_allowed", normalized_class, normalized_side_effect)

    if normalized_tool == "web_search_draft":
        if normalized_class != "read_only" or normalized_side_effect != "read_only":
            return _decision(False, "draft_search_requires_read_only_contract", normalized_class, normalized_side_effect)
        return _decision(True, "draft_search_network_disabled", normalized_class, normalized_side_effect)

    if normalized_tool == "github_draft_bundle":
        if normalized_class != "workspace_write" or normalized_side_effect != "workspace_write":
            return _decision(False, "github_draft_requires_workspace_write_contract", normalized_class, normalized_side_effect)
        requested_path = str(
            payload.get("output_path")
            or payload.get("path")
            or payload.get("output_dir")
            or payload.get("target_path")
            or ""
        ).strip()
        if requested_path and not _is_allowed_github_draft_path(requested_path):
            return _decision(False, "github_draft_output_path_not_allowed", normalized_class, normalized_side_effect, output_path=requested_path)
        return _decision(True, "github_draft_bundle_allowed", normalized_class, normalized_side_effect, output_path="workspace/github_outbox")

    if normalized_tool not in {"read_file", "write_file", "list_dir"}:
        return _decision(False, "l4_tool_not_allowlisted", normalized_class, normalized_side_effect)

    path = str(payload.get("path") or "").strip()
    if not path:
        return _decision(False, "l4_path_required", normalized_class, normalized_side_effect)
    normalized_path = path.replace("\\", "/").lstrip("/")
    parts = [part for part in normalized_path.split("/") if part]
    if any(part == ".." for part in parts):
        return _decision(False, "l4_parent_traversal_blocked", normalized_class, normalized_side_effect, output_path=path)
    if any(part in {".git", ".env", "__pycache__"} or part.startswith(".env") for part in parts):
        return _decision(False, "l4_sensitive_path_blocked", normalized_class, normalized_side_effect, output_path=path)

    if normalized_tool == "write_file":
        if normalized_class != "workspace_write" or normalized_side_effect != "workspace_write":
            return _decision(False, "l4_write_requires_workspace_write_contract", normalized_class, normalized_side_effect, output_path=path)
        return _decision(True, "l4_workspace_write_allowed", normalized_class, normalized_side_effect, output_path=path)

    if normalized_class != "read_only" or normalized_side_effect != "read_only":
        return _decision(False, "l4_read_requires_read_only_contract", normalized_class, normalized_side_effect, output_path=path)
    return _decision(True, "l4_read_allowed", normalized_class, normalized_side_effect, output_path=path)


def _is_allowed_github_draft_path(path: str) -> bool:
    normalized = str(path or "").strip().replace("\\", "/").strip("/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized in {"workspace/github_outbox", "github_outbox"}:
        return True
    return normalized in GITHUB_DRAFT_BUNDLE_FILES


def resolve_allowed_outbox_path(output_path: str, *, workspace_root: Any = ".") -> Optional[Path]:
    raw = str(output_path or "").strip()
    if not raw:
        return None

    root = Path(workspace_root).resolve(strict=False)
    target = Path(raw)
    if not target.is_absolute():
        target = root / target
    target = target.resolve(strict=False)

    allowed_paths = {
        (root / relative_path).resolve(strict=False)
        for relative_path in ALLOWED_GITHUB_OUTBOX_PATHS
    }
    if target not in allowed_paths:
        return None

    try:
        target.relative_to(root)
    except ValueError:
        return None

    return target


def is_executable_sensitive_output(output_path: str) -> bool:
    raw = str(output_path or "").strip().replace("\\", "/")
    if not raw:
        return False

    normalized = raw
    while normalized.startswith("./"):
        normalized = normalized[2:]
    for pattern in EXECUTABLE_SENSITIVE_PATTERNS:
        if fnmatch.fnmatch(normalized, pattern):
            return True
        if fnmatch.fnmatch(Path(normalized).name, pattern):
            return True
    return False


def build_tool_trace_event(
    *,
    tool_name: str,
    tool_class: Any,
    input_summary: str = "",
    output_path: str = "",
    output_summary: str = "",
    side_effect_level: Any = SideEffectLevel.NONE,
    policy_decision: Optional[Dict[str, Any]] = None,
    executor_approved: bool = False,
    status: str = "",
    error: str = "",
    task_id: str = "",
    tool_input_full: Optional[Dict[str, Any]] = None,
    trace_id: str = "",
    origin: str = "",
) -> Dict[str, Any]:
    event = {
        "trace_id": str(trace_id or uuid.uuid4().hex),
        "task_id": str(task_id or ""),
        "timestamp": time.time(),
        "origin": str(origin or ""),
        "tool_name": str(tool_name or ""),
        "tool_class": _enum_value(tool_class),
        "input_summary": str(input_summary or ""),
        "output_path": str(output_path or ""),
        "output_summary": str(output_summary or ""),
        "side_effect_level": _enum_value(side_effect_level),
        "policy_decision": dict(policy_decision or {}),
        "executor_approved": bool(executor_approved),
        "status": str(status or ""),
        "error": str(error or ""),
    }
    if isinstance(tool_input_full, dict):
        event["tool_input_full"] = dict(tool_input_full)
    return event


def _decision(
    ok: bool,
    reason: str,
    tool_class: Any,
    side_effect_level: Any,
    *,
    output_path: str = "",
) -> Dict[str, Any]:
    return ToolPolicyDecision(
        ok=bool(ok),
        reason=str(reason or ""),
        tool_class=_enum_value(tool_class),
        side_effect_level=_enum_value(side_effect_level),
        output_path=str(output_path or ""),
    ).to_dict()


def _parse_tool_class(value: Any) -> Optional[ToolClass]:
    normalized = _enum_value(value)
    for item in ToolClass:
        if item.value == normalized:
            return item
    return None


def _parse_side_effect_level(value: Any) -> Optional[SideEffectLevel]:
    normalized = _enum_value(value)
    for item in SideEffectLevel:
        if item.value == normalized:
            return item
    return None


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value or "").strip().lower()


def _looks_like_external_write(action: str, tool_name: str) -> bool:
    text = f"{tool_name} {action}"
    markers = (
        "push",
        "create_pr",
        "create pr",
        "open_pr",
        "open pr",
        "create_issue",
        "create issue",
        "external_write",
    )
    return any(marker in text for marker in markers)


def _looks_like_workspace_write(action: str, output_path: str) -> bool:
    write_actions = {"write", "write_file", "overwrite", "append", "append_file", "mkdir"}
    if action in write_actions:
        return True
    return bool(output_path)


def _looks_like_read(action: str, tool_name: str) -> bool:
    read_actions = {"read", "read_file", "list", "list_files", "exists", "git_status", "git_diff"}
    if action in read_actions:
        return True
    read_tools = {"github_issue_reader", "git_status", "git_diff"}
    return tool_name in read_tools
