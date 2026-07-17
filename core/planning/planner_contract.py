from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple


PLANNER_CONTRACT_VERSION = "planner_contract.v1"
PLANNER_STEP_CONTRACT_VERSION = "planner_step_contract.v2"
FILE_CONTENT_TEMPLATE = "{{file_content}}"
PREVIOUS_RESULT_TEMPLATE = "{{previous_result}}"

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


def read_file_step(path: str, *, scope: str = "", **extra: Any) -> Dict[str, Any]:
    step = _step_base("read_file", **extra)
    step["path"] = _clean_text(path)
    if scope:
        step["scope"] = _clean_text(scope)
    return step


def llm_step(
    *,
    mode: str,
    prompt: str,
    template_fields: Optional[List[str]] = None,
    required_runtime_features: Optional[List[str]] = None,
    **extra: Any,
) -> Dict[str, Any]:
    step = _step_base("llm", **extra)
    step["mode"] = _clean_text(mode)
    step["prompt"] = _clean_text(prompt)
    fields = list(template_fields or [])
    features = list(required_runtime_features or [])
    if fields:
        step["template_fields"] = fields
    if features:
        step["required_runtime_features"] = features
    return step


def llm_file_template_step(*, mode: str, prompt: str, **extra: Any) -> Dict[str, Any]:
    return llm_step(
        mode=mode,
        prompt=prompt,
        template_fields=["prompt"],
        required_runtime_features=["template_substitution"],
        **extra,
    )


def write_previous_result_step(path: str, *, scope: str = "", **extra: Any) -> Dict[str, Any]:
    step = _step_base("write_file", **extra)
    step["path"] = _clean_text(path)
    step["scope"] = _clean_text(scope)
    step["use_previous_text"] = True
    step["input_binding"] = "previous_result"
    step["declared_input"] = "previous_result"
    return step


def append_previous_result_step(path: str, *, scope: str = "", **extra: Any) -> Dict[str, Any]:
    step = _step_base("append_file", **extra)
    step["path"] = _clean_text(path)
    step["scope"] = _clean_text(scope)
    step["use_previous_text"] = True
    step["input_binding"] = "previous_result"
    step["declared_input"] = "previous_result"
    return step


def planner_contract_error(*, reason: str, steps: Any = None) -> Dict[str, Any]:
    return {
        "ok": False,
        "planner_contract_error": True,
        "planner_contract_version": PLANNER_STEP_CONTRACT_VERSION,
        "error": _clean_text(reason) or "planner contract error",
        "steps": steps if isinstance(steps, list) else [],
    }


def annotate_plan_contract(result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return result
    steps = result.get("steps")
    validation = validate_step_contracts(steps)
    result["planner_contract_version"] = PLANNER_STEP_CONTRACT_VERSION
    result["runtime_requirements"] = _collect_runtime_requirements(steps)
    result["step_contracts"] = _collect_step_contracts(steps)
    meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
    meta["planner_contract_version"] = PLANNER_STEP_CONTRACT_VERSION
    meta["runtime_requirements"] = list(result["runtime_requirements"])
    meta["step_contracts"] = list(result["step_contracts"])
    result["meta"] = meta
    if not validation["ok"]:
        result["ok"] = False
        result["planner_contract_error"] = True
        result["error"] = "; ".join(validation["errors"])
        meta["planner_contract_error"] = True
        meta["planner_contract_errors"] = list(validation["errors"])
        result["meta"] = meta
    return result


def validate_step_contracts(steps: Any) -> Dict[str, Any]:
    errors: List[str] = []
    if not isinstance(steps, list):
        return {"ok": False, "errors": ["steps_not_list"]}
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            errors.append(f"step_{index}:not_dict")
            continue
        step_type = _clean_text(step.get("type"))
        if step_type in {"write_file", "append_file"}:
            content = _clean_text(step.get("content"))
            if content == PREVIOUS_RESULT_TEMPLATE:
                errors.append(f"step_{index}:{step_type}:previous_result_template_without_contract")
            if step.get("use_previous_text") is True:
                declared = _clean_text(step.get("declared_input") or step.get("input_binding"))
                if declared != "previous_result":
                    errors.append(f"step_{index}:{step_type}:missing_previous_result_binding")
        for field in ("prompt", "prompt_template", "content"):
            value = step.get(field)
            if not isinstance(value, str):
                continue
            if "{{" in value and "}}" in value:
                template_fields = step.get("template_fields")
                features = step.get("required_runtime_features")
                if field not in template_fields if isinstance(template_fields, list) else True:
                    errors.append(f"step_{index}:{step_type}:{field}:missing_template_fields")
                if "template_substitution" not in features if isinstance(features, list) else True:
                    errors.append(f"step_{index}:{step_type}:{field}:missing_template_runtime_feature")
    return {"ok": not errors, "errors": errors}


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


def _step_base(step_type: str, **extra: Any) -> Dict[str, Any]:
    step = dict(extra)
    step["type"] = _clean_text(step_type)
    step["planner_contract_version"] = PLANNER_STEP_CONTRACT_VERSION
    step["legacy_plan_contract"] = False
    return step


def _collect_runtime_requirements(steps: Any) -> List[str]:
    requirements: List[str] = []
    if not isinstance(steps, list):
        return requirements
    for step in steps:
        if not isinstance(step, dict):
            continue
        values = step.get("required_runtime_features")
        if not isinstance(values, list):
            continue
        for value in values:
            text = _clean_text(value)
            if text and text not in requirements:
                requirements.append(text)
    return requirements


def _collect_step_contracts(steps: Any) -> List[Dict[str, Any]]:
    contracts: List[Dict[str, Any]] = []
    if not isinstance(steps, list):
        return contracts
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            contracts.append({"index": index, "type": "invalid", "contract_version": PLANNER_STEP_CONTRACT_VERSION})
            continue
        contracts.append(
            {
                "index": index,
                "type": _clean_text(step.get("type")),
                "contract_version": _clean_text(step.get("planner_contract_version")) or PLANNER_STEP_CONTRACT_VERSION,
                "declared_input": _clean_text(step.get("declared_input") or step.get("input_binding")),
                "template_fields": list(step.get("template_fields")) if isinstance(step.get("template_fields"), list) else [],
                "required_runtime_features": (
                    list(step.get("required_runtime_features"))
                    if isinstance(step.get("required_runtime_features"), list)
                    else []
                ),
                "legacy_plan_contract": bool(step.get("legacy_plan_contract", False)),
            }
        )
    return contracts


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
