from __future__ import annotations

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

