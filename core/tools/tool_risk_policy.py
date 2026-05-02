from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Dict


RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"


HIGH_RISK_TOOL_MARKERS = (
    "delete",
    "remove",
    "rm",
    "shell",
    "command",
    "terminal",
    "git_push",
    "push",
    "repo_settings",
    "settings",
)

HIGH_RISK_COMMAND_PATTERNS = (
    r"\brm\b",
    r"\bdel\b",
    r"\brmdir\b",
    r"\bRemove-Item\b",
    r"\bgit\s+push\b",
    r"\bgit\s+reset\b",
    r"\bgit\s+clean\b",
    r"\bchmod\b",
    r"\bicacls\b",
)

SECRET_PATH_MARKERS = (
    ".env",
    "secret",
    "secrets",
    "credential",
    "credentials",
    "token",
    "tokens",
    "key",
    "keys",
)

SYSTEM_PATH_PREFIXES = (
    "/etc",
    "/var",
    "/usr",
    "/bin",
    "/sbin",
    "/system",
    "c:/windows",
    "c:/program files",
    "c:/program files (x86)",
)


def assess_tool_risk(
    *,
    tool: Any,
    args: Any = None,
    schema: Any = None,
    policy: Any = None,
) -> Dict[str, Any]:
    """
    Estimate tool risk only.

    This policy intentionally does not allow, deny, stop, replan, or execute.
    The controller owns the final decision.
    """
    tool_name = str(tool or "").strip().lower()
    payload = args if isinstance(args, dict) else {}
    spec = schema if isinstance(schema, dict) else {}
    l4_policy = policy if isinstance(policy, dict) else {}

    reasons = []

    schema_risk = str(spec.get("risk_level") or "").strip().lower()
    if schema_risk == "high":
        reasons.append("schema_high_risk")

    tool_text = tool_name.replace("-", "_")
    if any(marker in tool_text for marker in HIGH_RISK_TOOL_MARKERS):
        reasons.append("high_risk_tool_name")

    command_text = _command_text(payload)
    if command_text and _matches_any(command_text, HIGH_RISK_COMMAND_PATTERNS):
        reasons.append("dangerous_command")

    path = _first_path(payload)
    if path:
        path_risk = _path_risk_reason(path)
        if path_risk:
            reasons.append(path_risk)

    side_effect = str(spec.get("side_effect_level") or l4_policy.get("side_effect_level") or "").strip().lower()
    tool_class = str(spec.get("tool_class") or l4_policy.get("tool_class") or "").strip().lower()
    if side_effect == "external_write" or tool_class == "external_write":
        reasons.append("external_write")

    if reasons:
        risk_level = RISK_HIGH
        risk_reason = reasons[0]
    elif side_effect == "workspace_write" or tool_class == "workspace_write":
        risk_level = RISK_MEDIUM
        risk_reason = "workspace_write"
    elif side_effect == "read_only" or tool_class == "read_only":
        risk_level = RISK_LOW
        risk_reason = "read_only"
    else:
        risk_level = RISK_LOW
        risk_reason = "no_high_risk_signal"

    return {
        "ok": True,
        "risk_level": risk_level,
        "risk_reason": risk_reason,
        "risk_reasons": reasons,
        "confirmation_required": risk_level == RISK_HIGH,
    }


def _command_text(args: Dict[str, Any]) -> str:
    for key in ("command", "command_text", "cmd", "text", "script"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _first_path(args: Dict[str, Any]) -> str:
    for key in ("path", "target_path", "output_path", "repo_path", "file_path"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _path_risk_reason(path: str) -> str:
    normalized = str(path or "").strip().replace("\\", "/").lower()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    compact_parts = [part for part in PurePosixPath(normalized).parts if part not in {"", "."}]

    if any(part == ".." for part in compact_parts):
        return "dangerous_path"
    if any(part == ".git" for part in compact_parts):
        return "repo_settings"
    if any(marker in compact_parts or marker in normalized for marker in SECRET_PATH_MARKERS):
        return "secrets_path"
    if any(normalized.startswith(prefix) for prefix in SYSTEM_PATH_PREFIXES):
        return "system_path"
    if re.match(r"^[a-z]:/", normalized) and not normalized.startswith("c:/users/"):
        return "system_path"
    return ""


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)
