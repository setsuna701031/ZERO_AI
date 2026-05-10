from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional


EXECUTION_CONTRACT_VERSION = "execution_contract.v1"

_ALLOWED_STEP_TYPES = {
    "noop",
    "read_file",
    "write_file",
    "append_file",
    "verify",
    "command",
    "run_python",
    "llm",
    "llm_generate",
    "code_edit",
    "function_fix",
    "multi_code_edit",
    "code_chain_analyze",
    "code_chain_repair",
    "code_chain_verify",
}


@dataclass(frozen=True)
class ExecutionContractResult:
    ok: bool
    step: Dict[str, Any]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def normalize_execution_step(raw_step: Any) -> ExecutionContractResult:
    errors: List[str] = []
    warnings: List[str] = []

    if raw_step is None:
        step = _base_step(step_type="noop")
        warnings.append("execution_step_missing")
    elif isinstance(raw_step, Mapping):
        step = dict(raw_step)
    else:
        return ExecutionContractResult(
            ok=False,
            step=_base_step(step_type="noop"),
            errors=[f"execution_step_not_mapping:{type(raw_step).__name__}"],
            warnings=[],
        )

    step_type = _clean_text(step.get("type") or step.get("action") or step.get("kind")).lower()
    if not step_type:
        step_type = "noop"

    step_type = _normalize_step_type(step_type)
    if step_type not in _ALLOWED_STEP_TYPES:
        warnings.append(f"execution_step_type_unknown:{step_type}")
        step_type = "noop"

    normalized = _base_step(step_type=step_type)
    normalized["path"] = _clean_optional_path(step.get("path") or step.get("target_path") or step.get("file_path"))
    normalized["target_path"] = _clean_optional_path(step.get("target_path") or step.get("path") or step.get("file_path"))
    normalized["content"] = _clean_text(step.get("content") or step.get("text") or step.get("body"))
    normalized["command"] = _clean_text(step.get("command") or step.get("cmd"))
    normalized["reason"] = _clean_text(step.get("reason") or step.get("why"))
    normalized["description"] = _clean_text(step.get("description") or step.get("goal"))
    normalized["metadata"] = _clean_metadata(step.get("metadata"))

    for key in (
        "scope",
        "depends_on",
        "planner_contract_action",
        "expected",
        "timeout_seconds",
        "atomic",
    ):
        if key in step:
            normalized[key] = _copy_safe_value(step.get(key))

    _validate_step(normalized, errors, warnings)

    normalized["contract_version"] = EXECUTION_CONTRACT_VERSION
    normalized["is_valid"] = not errors
    normalized["contract_errors"] = list(errors)
    normalized["contract_warnings"] = list(warnings)

    return ExecutionContractResult(
        ok=not errors,
        step=normalized,
        errors=errors,
        warnings=warnings,
    )


def validate_execution_step(step: Any) -> ExecutionContractResult:
    return normalize_execution_step(step)


def sanitize_execution_step(step: Any) -> Dict[str, Any]:
    return normalize_execution_step(step).step


def _base_step(step_type: str) -> Dict[str, Any]:
    return {
        "contract_version": EXECUTION_CONTRACT_VERSION,
        "type": step_type,
        "path": None,
        "target_path": None,
        "content": "",
        "command": "",
        "reason": "",
        "description": "",
        "metadata": {},
        "is_valid": True,
        "contract_errors": [],
        "contract_warnings": [],
    }


def _normalize_step_type(value: str) -> str:
    aliases = {
        "verify_file": "verify",
        "run_command": "command",
        "shell": "command",
        "write": "write_file",
        "read": "read_file",
        "append": "append_file",
        "fix": "code_edit",
        "repair": "code_chain_repair",
    }
    return aliases.get(value, value)


def _validate_step(step: Dict[str, Any], errors: List[str], warnings: List[str]) -> None:
    step_type = str(step.get("type") or "").strip().lower()

    if step_type in {"read_file", "write_file", "append_file", "verify"}:
        if not step.get("target_path") and not step.get("path"):
            errors.append(f"{step_type}:missing_path")

    if step_type in {"write_file", "append_file"} and step.get("content") == "":
        warnings.append(f"{step_type}:empty_content")

    if step_type in {"command", "run_python"}:
        if not step.get("command"):
            errors.append(f"{step_type}:missing_command")

    if step_type in {"code_edit", "function_fix", "multi_code_edit", "code_chain_repair", "code_chain_verify"}:
        if not step.get("target_path") and not step.get("path") and not step.get("description"):
            warnings.append(f"{step_type}:missing_target_or_description")


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

        cleaned_value = _copy_safe_value(item)
        if cleaned_value is not None or item is None:
            cleaned[clean_key] = cleaned_value

    return cleaned


def _copy_safe_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    if isinstance(value, list):
        return [
            item for item in value
            if isinstance(item, (str, int, float, bool)) or item is None
        ]

    if isinstance(value, Mapping):
        safe: Dict[str, Any] = {}
        for key, item in value.items():
            clean_key = _clean_text(key)
            if not clean_key:
                continue
            if isinstance(item, (str, int, float, bool)) or item is None:
                safe[clean_key] = item
        return safe

    return None