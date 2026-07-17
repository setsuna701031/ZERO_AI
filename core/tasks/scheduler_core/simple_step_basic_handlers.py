from __future__ import annotations

import json
import os
from typing import Any, Dict


def handle_simple_noop_step(step: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": True,
        "type": "noop",
        "message": str(step.get("message") or "noop ok"),
    }


def handle_simple_ensure_file_step(
    scheduler,
    *,
    step: Dict[str, Any],
    task_dir: str,
    step_scope: str,
    guard_result: Dict[str, Any],
) -> Dict[str, Any]:
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

def handle_simple_write_file_step(
    scheduler,
    *,
    task: Dict[str, Any],
    step: Dict[str, Any],
    task_dir: str,
    step_scope: str,
    legacy_template_detected,
    contract_failure,
    resolve_previous_result_text_for_contract,
    render_simple_step_template,
    resolve_simple_runtime_output_path,
    step_contract_metadata,
) -> Dict[str, Any]:
    raw_path = str(step.get("path") or "").strip()
    if not raw_path:
        raise ValueError("write_file step missing path")

    if legacy_template_detected(step):
        return contract_failure(
            step=step,
            error_type="legacy_contract_detected",
            message="legacy previous_result template is not supported by simple runtime",
        )

    if bool(step.get("use_previous_text", False)):
        ok, content, failure = resolve_previous_result_text_for_contract(scheduler, task, step)
        if not ok:
            return failure
    else:
        content = step.get("content", "")

    if content is None:
        content = ""
    content = render_simple_step_template(
        content,
        scheduler=scheduler,
        task=task,
    )

    full_path = resolve_simple_runtime_output_path(
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
        **step_contract_metadata(step),
    }

def handle_simple_append_file_step(
    scheduler,
    *,
    task: Dict[str, Any],
    step: Dict[str, Any],
    task_dir: str,
    step_scope: str,
    guard_result: Dict[str, Any],
    legacy_template_detected,
    contract_failure,
    resolve_previous_result_text_for_contract,
    render_simple_step_template,
    step_contract_metadata,
) -> Dict[str, Any]:
    raw_path = str(step.get("path") or "").strip()
    if not raw_path:
        raise ValueError("append_file step missing path")

    if legacy_template_detected(step):
        return contract_failure(
            step=step,
            error_type="legacy_contract_detected",
            message="legacy previous_result template is not supported by simple runtime",
        )

    if bool(step.get("use_previous_text", False)):
        ok, content, failure = resolve_previous_result_text_for_contract(scheduler, task, step)
        if not ok:
            return failure
    else:
        content = step.get("content", "")

    if content is None:
        content = ""
    content = render_simple_step_template(content, scheduler=scheduler, task=task)

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
        **step_contract_metadata(step),
    }

def handle_simple_read_file_step(
    scheduler,
    *,
    task: Dict[str, Any],
    step: Dict[str, Any],
    task_dir: str,
    step_scope: str,
) -> Dict[str, Any]:
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

def handle_simple_verify_step(
    scheduler,
    *,
    task: Dict[str, Any],
    step: Dict[str, Any],
    task_dir: str,
    step_scope: str,
) -> Dict[str, Any]:
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

