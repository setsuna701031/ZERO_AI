from __future__ import annotations

import copy
import json
import traceback

from typing import Any, Dict

from core.runtime.task_runner_changed_files_helpers import extract_changed_files_from_step_result
from core.runtime.task_runner_engineering_identity_helpers import (
    runtime_action_id,
    runtime_action_metadata,
    runtime_linked_session_node,
    runtime_step_action_type,
    runtime_step_id,
    runtime_step_target,
)


def stringify_failure_message(error: Any) -> str:
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        return json.dumps(error, ensure_ascii=False)
    if isinstance(error, str):
        return error
    if error is None:
        return ""
    return str(error)


def safe_update_current_engineering_action(
    *,
    runtime: Any,
    debug: bool,
    task: Dict[str, Any],
    step: Any,
    step_index: int,
    current_tick: int,
    trace_tick: int,
) -> None:
    fn = getattr(runtime, "update_current_engineering_action", None)
    if not callable(fn):
        return
    try:
        fn(
            task=task,
            action_type=runtime_step_action_type(step),
            target=runtime_step_target(step),
            step_id=runtime_step_id(step, step_index),
            action_id=runtime_action_id(task=task, step=step, step_index=step_index),
            linked_session_node=runtime_linked_session_node(task=task, step=step, step_index=step_index),
            metadata=runtime_action_metadata(step=step, step_index=step_index, current_tick=current_tick, trace_tick=trace_tick),
        )
    except Exception:
        if debug:
            traceback.print_exc()


def safe_complete_engineering_action(
    *,
    runtime: Any,
    debug: bool,
    task: Dict[str, Any],
    step: Any,
    step_result: Dict[str, Any],
    step_index: int,
    current_tick: int,
    trace_tick: int,
) -> None:
    fn = getattr(runtime, "complete_engineering_action", None)
    if not callable(fn):
        return
    try:
        fn(
            task=task,
            action_type=runtime_step_action_type(step),
            target=runtime_step_target(step),
            step_id=runtime_step_id(step, step_index),
            action_id=runtime_action_id(task=task, step=step, step_index=step_index),
            linked_session_node=runtime_linked_session_node(task=task, step=step, step_index=step_index),
            result=copy.deepcopy(step_result) if isinstance(step_result, dict) else {"raw_result": step_result},
            changed_files=extract_changed_files_from_step_result(step_result),
            tick=trace_tick if trace_tick is not None else current_tick,
            metadata=runtime_action_metadata(step=step, step_index=step_index, current_tick=current_tick, trace_tick=trace_tick),
        )
    except Exception:
        if debug:
            traceback.print_exc()


def safe_fail_engineering_action(
    *,
    runtime: Any,
    debug: bool,
    task: Dict[str, Any],
    step: Any,
    step_result: Dict[str, Any],
    step_index: int,
    current_tick: int,
    trace_tick: int,
) -> None:
    fn = getattr(runtime, "fail_engineering_action", None)
    if not callable(fn):
        return
    try:
        error = ""
        if isinstance(step_result, dict):
            error = stringify_failure_message(step_result.get("error") or step_result.get("message") or "")
        fn(
            task=task,
            action_type=runtime_step_action_type(step),
            target=runtime_step_target(step),
            step_id=runtime_step_id(step, step_index),
            action_id=runtime_action_id(task=task, step=step, step_index=step_index),
            linked_session_node=runtime_linked_session_node(task=task, step=step, step_index=step_index),
            error=error,
            result=copy.deepcopy(step_result) if isinstance(step_result, dict) else {"raw_result": step_result},
            tick=trace_tick if trace_tick is not None else current_tick,
            metadata=runtime_action_metadata(step=step, step_index=step_index, current_tick=current_tick, trace_tick=trace_tick),
        )
    except Exception:
        if debug:
            traceback.print_exc()


def safe_block_engineering_action(
    *,
    runtime: Any,
    debug: bool,
    task: Dict[str, Any],
    step: Any,
    step_result: Dict[str, Any],
    step_index: int,
    current_tick: int,
    trace_tick: int,
    reason: str = "",
) -> None:
    fn = getattr(runtime, "block_engineering_action", None)
    if not callable(fn):
        return
    try:
        resolved_reason = str(reason or "").strip()
        if not resolved_reason and isinstance(step_result, dict):
            resolved_reason = str(step_result.get("policy_reason") or step_result.get("error") or step_result.get("message") or "blocked")
        fn(
            task=task,
            action_type=runtime_step_action_type(step),
            target=runtime_step_target(step),
            step_id=runtime_step_id(step, step_index),
            action_id=runtime_action_id(task=task, step=step, step_index=step_index),
            linked_session_node=runtime_linked_session_node(task=task, step=step, step_index=step_index),
            reason=resolved_reason,
            result=copy.deepcopy(step_result) if isinstance(step_result, dict) else {"raw_result": step_result},
            tick=trace_tick if trace_tick is not None else current_tick,
            metadata=runtime_action_metadata(step=step, step_index=step_index, current_tick=current_tick, trace_tick=trace_tick),
        )
    except Exception:
        if debug:
            traceback.print_exc()


def safe_record_rollback_restore_action(
    *,
    runtime: Any,
    debug: bool,
    task: Dict[str, Any],
    step: Any,
    rollback_result: Dict[str, Any],
    step_index: int,
    current_tick: int,
    trace_tick: int,
) -> None:
    fn = getattr(runtime, "record_rollback_restore_action", None)
    if not callable(fn):
        return
    try:
        fn(
            task=task,
            target=runtime_step_target(step),
            step_id=runtime_step_id(step, step_index) + ":rollback_restore",
            action_id=runtime_action_id(task=task, step=step, step_index=step_index) + "_rollback_restore",
            linked_session_node=runtime_linked_session_node(task=task, step=step, step_index=step_index),
            result=copy.deepcopy(rollback_result) if isinstance(rollback_result, dict) else {},
            changed_files=extract_changed_files_from_step_result(rollback_result),
            tick=trace_tick if trace_tick is not None else current_tick,
        )
    except Exception:
        if debug:
            traceback.print_exc()
