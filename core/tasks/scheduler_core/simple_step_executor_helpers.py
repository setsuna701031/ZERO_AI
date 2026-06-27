from __future__ import annotations

import copy
import os
from typing import Any, Dict, Optional, Tuple


SIMPLE_RUNTIME_CONTRACT_VERSION = "simple_runtime_contract.v1"

from .simple_step_text_helpers import _extract_text_deep, _legacy_template_detected
from .simple_step_basic_handlers import handle_simple_append_file_step, handle_simple_ensure_file_step, handle_simple_noop_step, handle_simple_read_file_step, handle_simple_verify_step, handle_simple_write_file_step


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
        return handle_simple_noop_step(step)

    if step_type == "ensure_file":
        return handle_simple_ensure_file_step(
            scheduler,
            step=step,
            task_dir=task_dir,
            step_scope=step_scope,
            guard_result=guard_result,
        )

    if step_type == "write_file":
        return handle_simple_write_file_step(
            scheduler,
            task=task,
            step=step,
            task_dir=task_dir,
            step_scope=step_scope,
            legacy_template_detected=_legacy_template_detected,
            contract_failure=_contract_failure,
            resolve_previous_result_text_for_contract=_resolve_previous_result_text_for_contract,
            render_simple_step_template=_render_simple_step_template,
            resolve_simple_runtime_output_path=_resolve_simple_runtime_output_path,
            step_contract_metadata=_step_contract_metadata,
        )

    if step_type == "append_file":
        return handle_simple_append_file_step(
            scheduler,
            task=task,
            step=step,
            task_dir=task_dir,
            step_scope=step_scope,
            guard_result=guard_result,
            legacy_template_detected=_legacy_template_detected,
            contract_failure=_contract_failure,
            resolve_previous_result_text_for_contract=_resolve_previous_result_text_for_contract,
            render_simple_step_template=_render_simple_step_template,
            step_contract_metadata=_step_contract_metadata,
        )

    if step_type == "read_file":
        return handle_simple_read_file_step(
            scheduler,
            task=task,
            step=step,
            task_dir=task_dir,
            step_scope=step_scope,
        )

    if step_type == "verify":
        return handle_simple_verify_step(
            scheduler,
            task=task,
            step=step,
            task_dir=task_dir,
            step_scope=step_scope,
        )

    return None
