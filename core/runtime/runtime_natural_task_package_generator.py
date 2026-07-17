from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import re
from typing import Any, Mapping, Sequence

RUNTIME_NATURAL_TASK_PACKAGE_GENERATOR_SCHEMA = (
    "zero.runtime.natural_task_package_generator.v1"
)
RUNTIME_OPERATOR_PACKAGE_SCHEMA = "zero.runtime.operator_package.v1"

_DEFAULT_TARGET_ROOT = "."
_DEFAULT_REQUESTED_MODE = "controlled"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return deepcopy(value)
    if isinstance(value, tuple):
        return list(deepcopy(value))
    return []


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _stable_token(prefix: str, payload: Mapping[str, Any], *, length: int = 16) -> str:
    digest = sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:length]
    return f"{prefix}-{digest}"


def _safe_relative_path(value: Any) -> str:
    path = _text(value).strip("'\"").replace("\\", "/")
    path = path.strip().strip(".,;:，。；：")

    if not path:
        return ""

    if re.match(r"^[A-Za-z]:/", path):
        return ""

    if path.startswith("/") or path.startswith("../") or "/../" in path:
        return ""

    parts = [part for part in path.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        return ""

    return "/".join(parts)


def _strip_quotes(value: str) -> str:
    text = _text(value)
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _file_token_pattern() -> str:
    return r"([A-Za-z0-9_.\-/]+\.[A-Za-z0-9_]+)"


def _build_file_change(
    *,
    task_text: str,
    path: str,
    operation: str,
    content: str,
) -> dict[str, Any]:
    return {
        "change_id": "natural-task-change-1",
        "change_type": "file_mutation",
        "description": task_text,
        "target_path": path,
        "path": path,
        "relative_path": path,
        "operation": operation,
        "content": content,
    }


def _extract_chinese_create_file_change(
    task_text: str,
) -> dict[str, Any] | None:
    text = _text(task_text)
    file_pattern = _file_token_pattern()

    patterns = (
        rf"^\s*在\s+([A-Za-z0-9_.\-/]+)\s*(?:建立|創建|新增|產生)\s+{file_pattern}\s*[，,]\s*內容(?:寫入|為|是)\s+(.+?)\s*$",
        rf"^\s*(?:建立|創建|新增|產生)\s+{file_pattern}\s*[，,]\s*內容(?:寫入|為|是)\s+(.+?)\s*$",
    )

    for index, pattern in enumerate(patterns):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue

        if index == 0:
            directory = _safe_relative_path(match.group(1))
            filename = _safe_relative_path(match.group(2))
            content = _strip_quotes(match.group(3))
            path = _safe_relative_path(f"{directory}/{filename}")
        else:
            path = _safe_relative_path(match.group(1))
            content = _strip_quotes(match.group(2))

        if path:
            return _build_file_change(
                task_text=task_text,
                path=path,
                operation="create_file",
                content=content,
            )

    return None


def _extract_english_create_file_change(
    task_text: str,
) -> dict[str, Any] | None:
    text = _text(task_text)
    file_pattern = _file_token_pattern()

    patterns = (
        rf"^\s*create\s+(?:a\s+)?file\s+(?:called|named)\s+{file_pattern}\s+in\s+([A-Za-z0-9_.\-/]+)\s+with\s+(?:content\s+)?(.+?)\s*$",
        rf"^\s*create\s+(?:a\s+)?file\s+(?:called|named)\s+{file_pattern}\s+with\s+(?:content\s+)?(.+?)\s*$",
        rf"^\s*create\s+{file_pattern}\s+with\s+(?:content\s+)?(.+?)\s*$",
    )

    for index, pattern in enumerate(patterns):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue

        if index == 0:
            filename = _safe_relative_path(match.group(1))
            directory = _safe_relative_path(match.group(2))
            content = _strip_quotes(match.group(3))
            path = _safe_relative_path(f"{directory}/{filename}")
        else:
            path = _safe_relative_path(match.group(1))
            content = _strip_quotes(match.group(2))

        if path:
            return _build_file_change(
                task_text=task_text,
                path=path,
                operation="create_file",
                content=content,
            )

    return None


def _extract_create_file_path(task_text: str) -> str:
    text = _text(task_text)

    patterns = (
        r"\bcalled\s+([A-Za-z0-9_.\-/]+)",
        r"\bnamed\s+([A-Za-z0-9_.\-/]+)",
        r"\bfile\s+([A-Za-z0-9_.\-/]+)",
        r"\bcreate\s+([A-Za-z0-9_.\-/]+\.[A-Za-z0-9_]+)",
        r"(?:建立|創建|新增|產生)\s+([A-Za-z0-9_.\-/]+\.[A-Za-z0-9_]+)",
    )

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            path = _safe_relative_path(match.group(1))
            if path:
                return path

    return ""


def _extract_append_file_change(task_text: str) -> dict[str, Any] | None:
    text = _text(task_text)
    file_pattern = _file_token_pattern()

    patterns = (
        rf"^\s*append\s+(.+?)\s+to\s+{file_pattern}\s*$",
        rf"^\s*add\s+(.+?)\s+to\s+{file_pattern}\s*$",
        rf"^\s*write\s+(.+?)\s+to\s+{file_pattern}\s*$",
    )

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue

        content = _strip_quotes(match.group(1))
        path = _safe_relative_path(match.group(2))

        if path:
            return _build_file_change(
                task_text=task_text,
                path=path,
                operation="append_file",
                content=content,
            )

    return None


def _extract_update_file_change(task_text: str) -> dict[str, Any] | None:
    text = _text(task_text)
    file_pattern = _file_token_pattern()

    patterns = (
        rf"^\s*update\s+{file_pattern}\s+with\s+(.+?)\s*$",
        rf"^\s*replace\s+{file_pattern}\s+with\s+(.+?)\s*$",
        rf"^\s*overwrite\s+{file_pattern}\s+with\s+(.+?)\s*$",
    )

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue

        path = _safe_relative_path(match.group(1))
        content = _strip_quotes(match.group(2))

        if path:
            return _build_file_change(
                task_text=task_text,
                path=path,
                operation="update_file",
                content=content,
            )

    return None


def _default_requested_changes(task_text: str) -> list[dict[str, Any]]:
    chinese_create_change = _extract_chinese_create_file_change(task_text)
    if chinese_create_change is not None:
        return [chinese_create_change]

    english_create_change = _extract_english_create_file_change(task_text)
    if english_create_change is not None:
        return [english_create_change]

    append_change = _extract_append_file_change(task_text)
    if append_change is not None:
        return [append_change]

    update_change = _extract_update_file_change(task_text)
    if update_change is not None:
        return [update_change]

    path = _extract_create_file_path(task_text)

    if path:
        return [
            _build_file_change(
                task_text=task_text,
                path=path,
                operation="create_file",
                content="",
            )
        ]

    return [
        {
            "change_id": "natural-task-change-1",
            "change_type": "controlled_task_request",
            "description": task_text,
            "target_path": "",
            "operation": "plan_only_until_authorized",
        }
    ]


def _authority_context(
    *,
    task_text: str,
    requested_mode: str,
    authority_context: Mapping[str, Any] | None,
) -> dict[str, Any]:
    context = _mapping(authority_context)
    context.setdefault("authority_source", "natural_task_package_generator")
    context.setdefault("requested_mode", requested_mode)
    context.setdefault("operator_service_required", True)
    context.setdefault("controlled_execution_required", True)
    context.setdefault("validation_required", True)
    context.setdefault("rollback_required", True)
    context.setdefault("direct_dispatch_allowed", False)
    context.setdefault("executor_bypass_allowed", False)
    context.setdefault("package_generator_input", task_text)
    return context


def build_runtime_operator_package_from_task(
    task_text: Any,
    *,
    target_root: Any = _DEFAULT_TARGET_ROOT,
    requested_mode: Any = _DEFAULT_REQUESTED_MODE,
    requested_changes: Sequence[Mapping[str, Any]] | None = None,
    authority_context: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic runtime operator package from natural task text.

    The helper is intentionally data-only. It only builds deterministic package
    dictionaries and never starts work directly.
    """

    normalized_task = _text(task_text)
    normalized_mode = _text(requested_mode) or _DEFAULT_REQUESTED_MODE
    normalized_target_root = _text(target_root) or _DEFAULT_TARGET_ROOT

    if not normalized_task:
        return {
            "schema": RUNTIME_NATURAL_TASK_PACKAGE_GENERATOR_SCHEMA,
            "ok": False,
            "package_generation_status": "denied",
            "denial_reason": "task_text_required",
            "runtime_operator_package": None,
            "direct_dispatch_requested": False,
            "executor_invoked": False,
            "execution_started": False,
            "task_executed": False,
            "runtime_state_mutated": False,
        }

    changes = _list(requested_changes)
    if not changes:
        changes = _default_requested_changes(normalized_task)

    seed = {
        "goal": normalized_task,
        "requested_mode": normalized_mode,
        "target_root": normalized_target_root,
        "requested_changes": changes,
    }

    task_id = _stable_token("task", seed)
    package_id = _stable_token("runtime-package", {"task_id": task_id, **seed})

    package = {
        "schema": RUNTIME_OPERATOR_PACKAGE_SCHEMA,
        "package_id": package_id,
        "task_id": task_id,
        "goal": normalized_task,
        "requested_mode": normalized_mode,
        "target_root": normalized_target_root,
        "requested_changes": changes,
        "authority_context": _authority_context(
            task_text=normalized_task,
            requested_mode=normalized_mode,
            authority_context=authority_context,
        ),
        "validation_required": True,
        "rollback_required": True,
        "metadata": _mapping(metadata),
    }

    return {
        "schema": RUNTIME_NATURAL_TASK_PACKAGE_GENERATOR_SCHEMA,
        "ok": True,
        "package_generation_status": "generated",
        "denial_reason": "",
        "runtime_operator_package": package,
        "package": deepcopy(package),
        "package_id": package_id,
        "task_id": task_id,
        "goal": normalized_task,
        "requested_mode": normalized_mode,
        "target_root": normalized_target_root,
        "validation_required": True,
        "rollback_required": True,
        "direct_dispatch_requested": False,
        "executor_invoked": False,
        "execution_started": False,
        "task_executed": False,
        "runtime_state_mutated": False,
    }


def runtime_operator_package_to_summary(
    generation_result: Mapping[str, Any],
) -> dict[str, Any]:
    result = _mapping(generation_result)
    package = _mapping(result.get("runtime_operator_package"))
    return {
        "schema": RUNTIME_NATURAL_TASK_PACKAGE_GENERATOR_SCHEMA,
        "ok": result.get("ok") is True,
        "package_generation_status": result.get("package_generation_status")
        or "denied",
        "package_id": package.get("package_id") or result.get("package_id") or "",
        "task_id": package.get("task_id") or result.get("task_id") or "",
        "goal": package.get("goal") or result.get("goal") or "",
        "requested_mode": package.get("requested_mode")
        or result.get("requested_mode")
        or "",
        "validation_required": package.get("validation_required") is True,
        "rollback_required": package.get("rollback_required") is True,
        "direct_dispatch_requested": False,
        "executor_invoked": False,
        "execution_started": False,
        "task_executed": False,
    }


def validate_generated_runtime_operator_package(
    package: Mapping[str, Any],
) -> dict[str, Any]:
    payload = _mapping(package)
    errors: list[str] = []

    required_fields = (
        "schema",
        "package_id",
        "task_id",
        "goal",
        "requested_mode",
        "target_root",
        "requested_changes",
        "authority_context",
        "validation_required",
        "rollback_required",
    )

    for field in required_fields:
        if field not in payload:
            errors.append(f"missing:{field}")

    if payload.get("schema") != RUNTIME_OPERATOR_PACKAGE_SCHEMA:
        errors.append("invalid:schema")
    if not _text(payload.get("package_id")):
        errors.append("invalid:package_id")
    if not _text(payload.get("task_id")):
        errors.append("invalid:task_id")
    if not _text(payload.get("goal")):
        errors.append("invalid:goal")
    if _text(payload.get("requested_mode")) != _DEFAULT_REQUESTED_MODE:
        errors.append("invalid:requested_mode")
    if not isinstance(payload.get("requested_changes"), list):
        errors.append("invalid:requested_changes")
    if not isinstance(payload.get("authority_context"), Mapping):
        errors.append("invalid:authority_context")
    if payload.get("validation_required") is not True:
        errors.append("invalid:validation_required")
    if payload.get("rollback_required") is not True:
        errors.append("invalid:rollback_required")

    authority = _mapping(payload.get("authority_context"))
    if authority.get("operator_service_required") is not True:
        errors.append("invalid:operator_service_required")
    if authority.get("controlled_execution_required") is not True:
        errors.append("invalid:controlled_execution_required")
    if authority.get("direct_dispatch_allowed") is not False:
        errors.append("invalid:direct_dispatch_allowed")
    if authority.get("executor_bypass_allowed") is not False:
        errors.append("invalid:executor_bypass_allowed")

    return {
        "schema": RUNTIME_NATURAL_TASK_PACKAGE_GENERATOR_SCHEMA,
        "ok": not errors,
        "valid": not errors,
        "errors": errors,
        "package_id": _text(payload.get("package_id")),
        "task_id": _text(payload.get("task_id")),
    }


__all__ = [
    "RUNTIME_NATURAL_TASK_PACKAGE_GENERATOR_SCHEMA",
    "RUNTIME_OPERATOR_PACKAGE_SCHEMA",
    "build_runtime_operator_package_from_task",
    "runtime_operator_package_to_summary",
    "validate_generated_runtime_operator_package",
]
