from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple


PLANNER_CONTRACT_VERSION = "planner_contract.v1"

_ALLOWED_ACTIONS = {
    "noop",
    "read_file",
    "write_file",
    "append_file",
    "verify_file",
    "run_command",
    "repair",
    "rollback",
}


@dataclass(frozen=True)
class PlannerContractResult:
    ok: bool
    payload: Dict[str, Any]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def normalize_planner_payload(raw_payload: Any) -> PlannerContractResult:
    errors: List[str] = []
    warnings: List[str] = []

    if raw_payload is None:
        raw: Dict[str, Any] = {}
        warnings.append("planner_payload_missing")
    elif isinstance(raw_payload, Mapping):
        raw = dict(raw_payload)
    else:
        return PlannerContractResult(
            ok=False,
            payload=_base_payload(action="noop"),
            errors=[f"planner_payload_not_mapping:{type(raw_payload).__name__}"],
            warnings=[],
        )

    action = _normalize_action(raw.get("action") or raw.get("type") or raw.get("kind"))
    if action not in _ALLOWED_ACTIONS:
        warnings.append(f"planner_action_unknown:{action}")
        action = "noop"

    payload = _base_payload(action=action)
    payload["goal"] = _clean_text(raw.get("goal") or raw.get("task") or raw.get("description"))
    payload["target_path"] = _clean_optional_path(
        raw.get("target_path") or raw.get("path") or raw.get("file_path") or raw.get("filename")
    )
    payload["content"] = _clean_text(raw.get("content") or raw.get("text") or raw.get("body"))
    payload["command"] = _clean_text(raw.get("command") or raw.get("cmd"))
    payload["reason"] = _clean_text(raw.get("reason") or raw.get("rationale") or raw.get("why"))
    payload["metadata"] = _clean_metadata(raw.get("metadata"))

    payload["raw_action"] = _clean_text(raw.get("action") or raw.get("type") or raw.get("kind"))
    payload["contract_version"] = PLANNER_CONTRACT_VERSION

    _validate_required_fields(payload, errors, warnings)

    payload["is_valid"] = not errors
    payload["contract_errors"] = list(errors)
    payload["contract_warnings"] = list(warnings)

    return PlannerContractResult(
        ok=not errors,
        payload=payload,
        errors=errors,
        warnings=warnings,
    )


def validate_planner_payload(payload: Any) -> PlannerContractResult:
    result = normalize_planner_payload(payload)
    return result


def sanitize_planner_payload(payload: Any) -> Dict[str, Any]:
    return normalize_planner_payload(payload).payload


def _base_payload(action: str) -> Dict[str, Any]:
    return {
        "contract_version": PLANNER_CONTRACT_VERSION,
        "action": action,
        "raw_action": "",
        "goal": "",
        "target_path": None,
        "content": "",
        "command": "",
        "reason": "",
        "metadata": {},
        "is_valid": True,
        "contract_errors": [],
        "contract_warnings": [],
    }


def _normalize_action(value: Any) -> str:
    text = _clean_text(value).lower().strip()
    if not text:
        return "noop"

    aliases = {
        "none": "noop",
        "no_op": "noop",
        "read": "read_file",
        "write": "write_file",
        "append": "append_file",
        "verify": "verify_file",
        "run": "run_command",
        "command": "run_command",
        "shell": "run_command",
        "fix": "repair",
        "self_repair": "repair",
        "revert": "rollback",
    }
    return aliases.get(text, text)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.replace("\x00", "").strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    return ""


def _clean_optional_path(value: Any) -> Optional[str]:
    text = _clean_text(value)
    if not text:
        return None

    normalized = text.replace("\\", "/").strip()
    while "//" in normalized:
        normalized = normalized.replace("//", "/")

    return normalized or None


def _clean_metadata(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}

    cleaned: Dict[str, Any] = {}
    for key, item in value.items():
        clean_key = _clean_text(key)
        if not clean_key:
            continue

        if isinstance(item, (str, int, float, bool)) or item is None:
            cleaned[clean_key] = item
        elif isinstance(item, list):
            cleaned[clean_key] = [
                entry for entry in item if isinstance(entry, (str, int, float, bool)) or entry is None
            ]
        elif isinstance(item, Mapping):
            cleaned[clean_key] = {
                _clean_text(k): v
                for k, v in item.items()
                if _clean_text(k) and (isinstance(v, (str, int, float, bool)) or v is None)
            }

    return cleaned


def _validate_required_fields(payload: Dict[str, Any], errors: List[str], warnings: List[str]) -> None:
    action = payload.get("action")

    if action in {"read_file", "write_file", "append_file", "verify_file"}:
        if not payload.get("target_path"):
            errors.append(f"{action}:missing_target_path")

    if action in {"write_file", "append_file"}:
        if payload.get("content") == "":
            warnings.append(f"{action}:empty_content")

    if action == "run_command":
        if not payload.get("command"):
            errors.append("run_command:missing_command")

    if action in {"repair", "rollback"}:
        if not payload.get("goal") and not payload.get("reason"):
            warnings.append(f"{action}:missing_goal_or_reason")