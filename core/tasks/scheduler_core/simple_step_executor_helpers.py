from __future__ import annotations

import copy
import os
from typing import Any, Dict, Optional, Tuple


SIMPLE_RUNTIME_CONTRACT_VERSION = "simple_runtime_contract.v1"


def _step_contract_metadata(step: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "contract_source": "planner",
        "contract_version": str(step.get("planner_contract_version") or ""),
        "planner_contract_version": str(step.get("planner_contract_version") or ""),
        "runtime_contract_version": SIMPLE_RUNTIME_CONTRACT_VERSION,
        "input_binding": str(step.get("input_binding") or ""),
        "declared_input": str(step.get("declared_input") or ""),
    }


def _contract_failure(
    *,
    step: Dict[str, Any],
    error_type: str,
    message: str,
) -> Dict[str, Any]:
    payload = {
        "ok": False,
        "type": str(step.get("type") or ""),
        "action": "runtime_contract_failed",
        "status": "failed",
        "error_type": error_type,
        "message": message,
        "final_answer": message,
        "error": {
            "type": error_type,
            "message": message,
            "retryable": False,
        },
    }
    payload.update(_step_contract_metadata(step))
    return payload


def _extract_text_from_task_previous_result(scheduler, task: Dict[str, Any]) -> str:
    """Extract previous step text for the declared previous_result contract."""
    extractor = getattr(scheduler, "_extract_text_from_previous_result", None)
    if callable(extractor):
        text = extractor(task)
        if isinstance(text, str) and text:
            return text

    return _extract_text_deep((task or {}).get("last_step_result"))


def _resolve_previous_result_text_for_contract(scheduler, task: Dict[str, Any], step: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    declared_input = str(step.get("declared_input") or "").strip()
    input_binding = str(step.get("input_binding") or "").strip()
    if declared_input != "previous_result" or input_binding != "previous_result":
        return False, "", _contract_failure(
            step=step,
            error_type="runtime_contract_mismatch",
            message="use_previous_text requires declared_input and input_binding to be previous_result",
        )

    last_step_result = (task or {}).get("last_step_result")
    if last_step_result in (None, "", [], {}):
        return False, "", _contract_failure(
            step=step,
            error_type="runtime_contract_mismatch",
            message="declared_input previous_result is missing",
        )

    previous_text = _extract_text_from_task_previous_result(scheduler, task)
    if not isinstance(previous_text, str) or previous_text == "":
        return False, "", _contract_failure(
            step=step,
            error_type="runtime_contract_mismatch",
            message="declared_input previous_result has no text payload",
        )

    return True, previous_text, {}


def _extract_text_deep(payload: Any, depth: int = 0) -> str:
    if depth > 12 or payload is None:
        return ""

    if isinstance(payload, str):
        return payload

    if isinstance(payload, dict):
        for key in (
            "text",
            "content",
            "message",
            "final_answer",
            "response",
            "answer",
            "summary",
            "summary_text",
            "stdout",
            "output_text",
        ):
            value = payload.get(key)
            if isinstance(value, str):
                return value

        for nested_key in (
            "result",
            "raw",
            "data",
            "payload",
            "output",
            "previous_result",
            "last_step_result",
            "runtime_execution_result",
            "adapter_payload",
        ):
            nested = payload.get(nested_key)
            text = _extract_text_deep(nested, depth + 1)
            if isinstance(text, str) and text:
                return text

    if isinstance(payload, list):
        for item in reversed(payload):
            text = _extract_text_deep(item, depth + 1)
            if isinstance(text, str) and text:
                return text

    return ""


def _render_simple_step_template(
    value: Any,
    *,
    scheduler,
    task: Dict[str, Any],
) -> str:
    text = "" if value is None else str(value)
    if "{{file_content}}" not in text:
        return text

    previous_text = _extract_text_from_task_previous_result(scheduler, task)
    text = text.replace("{{file_content}}", previous_text)
    return text


def _resolve_simple_runtime_output_path(
    scheduler,
    *,
    raw_path: str,
    task_dir: str,
    step_scope: str,
) -> str:
    return scheduler._resolve_step_path(
        raw_path=raw_path,
        task_dir=task_dir,
        shared_dir=scheduler.shared_dir,
        scope=step_scope,
    )


def _legacy_template_detected(step: Dict[str, Any]) -> bool:
    for key in ("content", "text", "body"):
        value = step.get(key)
        if isinstance(value, str) and "{{previous_result" in value:
            return True
    return False


def prepare_simple_step_guard(
    scheduler,
    step: Dict[str, Any],
    step_type: str,
    step_scope: str,
) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    prepared_step = copy.deepcopy(step)
    guard_step = copy.deepcopy(prepared_step)
    effective_scope = step_scope

    if step_type == "run_python":
        run_path = str(prepared_step.get("path") or "").strip()
        if not run_path:
            raise ValueError("run_python step missing path")
        guard_step = {
            "type": "command",
            "command": f'{scheduler.sys_executable if hasattr(scheduler, "sys_executable") else __import__("sys").executable} "{run_path}"',
        }

    elif step_type == "verify":
        prepared_step = scheduler._normalize_verify_step(prepared_step)
        effective_scope = scheduler._normalize_step_scope(prepared_step.get("scope", None))
        guard_step = {
            "type": "noop",
            "message": "verify",
        }

    elif step_type == "ensure_file":
        raw_path = str(prepared_step.get("path") or "").strip()
        if not raw_path:
            raise ValueError("ensure_file step missing path")
        guard_step = {
            "type": "write_file",
            "path": raw_path,
            "content": "",
            "scope": effective_scope,
        }

    elif step_type == "append_file":
        raw_path = str(prepared_step.get("path") or "").strip()
        if not raw_path:
            raise ValueError("append_file step missing path")
        guard_step = {
            "type": "append_file",
            "path": raw_path,
            "content": str(prepared_step.get("content") or ""),
            "scope": effective_scope,
        }

    elif step_type == "code_edit":
        raw_path = str(prepared_step.get("path") or prepared_step.get("file") or "").strip()
        if not raw_path:
            raise ValueError("code_edit step missing path")

        edit_mode = str(prepared_step.get("edit_mode") or "").strip().lower()
        if edit_mode == "direct_workspace_edit":
            effective_scope = "shared"

        guard_step = {
            "type": "write_file",
            "path": raw_path,
            "content": "",
            "scope": effective_scope,
            "edit_mode": edit_mode,
            "target_policy": str(prepared_step.get("target_policy") or ""),
        }

    return prepared_step, guard_step, effective_scope


def execute_simple_basic_step(
    scheduler,
    task: Dict[str, Any],
    step: Dict[str, Any],
    step_type: str,
    task_dir: str,
    step_scope: str,
    guard_result: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if step_type == "noop":
        return {
            "ok": True,
            "type": "noop",
            "message": str(step.get("message") or "noop ok"),
        }

    if step_type == "ensure_file":
        raw_path = str(step.get("path") or "").strip()
        if not raw_path:
            raise ValueError("ensure_file step missing path")

        if str(step_scope or "").strip().lower() == "shared":
            full_path = scheduler._resolve_step_path(
                raw_path=raw_path,
                task_dir=task_dir,
                shared_dir=scheduler.shared_dir,
                scope="shared",
            )
        else:
            full_path = scheduler._resolve_guard_target_path(
                raw_path=raw_path,
                task_dir=task_dir,
                scope=step_scope,
                resolved_path=str(guard_result.get("resolved_path") or ""),
            )

        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        created = False
        if not os.path.exists(full_path):
            with open(full_path, "w", encoding="utf-8") as f:
                f.write("")
            created = True

        return {
            "type": "ensure_file",
            "path": raw_path,
            "full_path": full_path,
            "scope": step_scope,
            "created": created,
            "preserved_existing": not created,
        }

    if step_type == "write_file":
        raw_path = str(step.get("path") or "").strip()
        if not raw_path:
            raise ValueError("write_file step missing path")

        if _legacy_template_detected(step):
            return _contract_failure(
                step=step,
                error_type="legacy_contract_detected",
                message="legacy previous_result template is not supported by simple runtime",
            )

        if bool(step.get("use_previous_text", False)):
            ok, content, failure = _resolve_previous_result_text_for_contract(scheduler, task, step)
            if not ok:
                return failure
        else:
            content = step.get("content", "")

        if content is None:
            content = ""
        content = _render_simple_step_template(
            content,
            scheduler=scheduler,
            task=task,
        )

        full_path = _resolve_simple_runtime_output_path(
            scheduler,
            raw_path=raw_path,
            task_dir=task_dir,
            step_scope=step_scope,
        )

        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "type": "write_file",
            "path": raw_path,
            "full_path": full_path,
            "scope": step_scope,
            "bytes": len(content.encode("utf-8")),
            "content": content,
            "used_previous_text": bool(step.get("use_previous_text", False)),
            **_step_contract_metadata(step),
        }

    if step_type == "append_file":
        raw_path = str(step.get("path") or "").strip()
        if not raw_path:
            raise ValueError("append_file step missing path")

        if _legacy_template_detected(step):
            return _contract_failure(
                step=step,
                error_type="legacy_contract_detected",
                message="legacy previous_result template is not supported by simple runtime",
            )

        if bool(step.get("use_previous_text", False)):
            ok, content, failure = _resolve_previous_result_text_for_contract(scheduler, task, step)
            if not ok:
                return failure
        else:
            content = step.get("content", "")

        if content is None:
            content = ""
        content = _render_simple_step_template(
            content,
            scheduler=scheduler,
            task=task,
        )

        if bool(step.get("ensure_trailing_newline", False)) and content and not content.endswith("\n"):
            content += "\n"

        if str(step_scope or "").strip().lower() == "shared":
            full_path = scheduler._resolve_step_path(
                raw_path=raw_path,
                task_dir=task_dir,
                shared_dir=scheduler.shared_dir,
                scope="shared",
            )
        else:
            full_path = scheduler._resolve_guard_target_path(
                raw_path=raw_path,
                task_dir=task_dir,
                scope=step_scope,
                resolved_path=str(guard_result.get("resolved_path") or ""),
            )

        if os.path.exists(full_path) and os.path.isdir(full_path):
            raise IsADirectoryError(f"append_file target is a directory: {full_path}")

        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        before_size = os.path.getsize(full_path) if os.path.exists(full_path) else 0

        with open(full_path, "a", encoding="utf-8", newline="") as f:
            f.write(content)

        after_size = os.path.getsize(full_path) if os.path.exists(full_path) else before_size

        return {
            "type": "append_file",
            "path": raw_path,
            "full_path": full_path,
            "scope": step_scope,
            "bytes_before": before_size,
            "bytes_after": after_size,
            "bytes_appended": max(0, after_size - before_size),
            "content": content,
            "chars_appended": len(content),
            "created": before_size == 0,
            "ensure_trailing_newline": bool(step.get("ensure_trailing_newline", False)),
            **_step_contract_metadata(step),
        }

    if step_type == "read_file":
        raw_path = str(step.get("path") or "").strip()
        if not raw_path:
            raise ValueError("read_file step missing path")

        full_path = scheduler._resolve_read_path_with_fallback(
            raw_path=raw_path,
            task_dir=task_dir,
            shared_dir=scheduler.shared_dir,
            scope=step_scope,
        )

        guard_check = scheduler.execution_guard.check_step(
            step={"type": "read_file", "path": full_path},
            task_dir=task_dir,
        )
        if not bool(guard_check.get("ok")):
            raise PermissionError(str(guard_check.get("error") or "guard blocked read"))

        if not os.path.exists(full_path):
            raise FileNotFoundError(f"file not found: {full_path}")

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        return {
            "type": "read_file",
            "path": raw_path,
            "full_path": full_path,
            "scope": step_scope,
            "content": content,
        }

    if step_type == "verify":
        contains = step.get("contains", None)
        equals = step.get("equals", None)
        exists = step.get("exists", None)
        path = str(step.get("path") or "").strip()

        if contains is None and equals is None and exists is None and not path:
            raise ValueError("verify step requires path / contains / equals / exists")

        target_text = ""
        full_path = ""

        if path:
            full_path = scheduler._resolve_read_path_with_fallback(
                raw_path=path,
                task_dir=task_dir,
                shared_dir=scheduler.shared_dir,
                scope=step_scope,
            )

            read_guard = scheduler.execution_guard.check_step(
                step={"type": "read_file", "path": full_path},
                task_dir=task_dir,
            )
            if not bool(read_guard.get("ok")):
                raise PermissionError(str(read_guard.get("error") or "guard blocked verify read"))

            file_exists = os.path.exists(full_path)

            if exists is True and not file_exists:
                raise FileNotFoundError(f"verify file not found: {full_path}")

            if exists is False and file_exists:
                raise RuntimeError(f"verify failed: file should not exist: {full_path}")

            if (contains is not None or equals is not None or exists is not False) and not file_exists:
                raise FileNotFoundError(f"verify file not found: {full_path}")

            if file_exists and (contains is not None or equals is not None):
                with open(full_path, "r", encoding="utf-8") as f:
                    target_text = f.read()
        else:
            last = task.get("last_step_result")
            if isinstance(last, dict):
                last_result = last.get("result")
                if isinstance(last_result, dict):
                    if "stdout" in last_result:
                        target_text = str(last_result.get("stdout") or "")
                    elif "content" in last_result:
                        target_text = str(last_result.get("content") or "")
                    else:
                        target_text = json.dumps(last_result, ensure_ascii=False)
                else:
                    target_text = str(last_result or "")

        if contains is not None:
            contains_text = str(contains)
            if contains_text not in target_text:
                raise RuntimeError(f"verify contains failed: '{contains_text}' not found")

        if equals is not None:
            expected = str(equals)
            if str(target_text).strip() != expected.strip():
                raise RuntimeError(
                    f"verify equals failed: expected exact match '{expected}', got '{str(target_text).strip()}'"
                )

        return {
            "type": "verify",
            "ok": True,
            "path": path,
            "full_path": full_path,
            "scope": step_scope,
            "contains": contains,
            "equals": equals,
            "exists": exists,
            "checked_text": target_text,
            "verified": True,
        }

    return None
