from __future__ import annotations

from pathlib import Path

TARGET = Path("core/runtime/task_runner.py")
MARKER = "ZERO_CONSOLIDATION_STAGE3B_TASKRUNNER_RESULT_SHAPE_V3"

PATCH = r'''
# ZERO_CONSOLIDATION_STAGE3B_TASKRUNNER_RESULT_SHAPE_V3
# Consolidation fix: preserve TaskRunner runtime_state shape for both success and
# authority-denied/failure results after removing runtime-gate monkey patches.

try:
    _zero_stage3b_base_run_task_tick_v3 = TaskRunner.run_task_tick

    def _zero_stage3b_runtime_state_from_task_v3(task, result=None):
        state = {}
        if isinstance(result, dict) and isinstance(result.get("runtime_state"), dict):
            state.update(result.get("runtime_state") or {})
        if isinstance(task, dict):
            runtime_state = task.get("runtime_state")
            if isinstance(runtime_state, dict):
                state.update(runtime_state)
            for key in (
                "operator_session_id",
                "runtime_mode",
                "current_step_index",
                "status",
                "task_id",
                "id",
            ):
                if task.get(key) is not None and key not in state:
                    state[key] = task.get(key)
        return state

    def _zero_stage3b_normalize_taskrunner_result_v3(task, result):
        if not isinstance(result, dict):
            return result

        runtime_state = _zero_stage3b_runtime_state_from_task_v3(task, result)

        if isinstance(task, dict) and task.get("operator_session_id"):
            runtime_state["operator_session_id"] = task.get("operator_session_id")

        if result.get("ok") is True:
            if result.get("status") == "completed":
                result["status"] = "finished"
            if runtime_state.get("status") == "completed":
                runtime_state["status"] = "finished"
            if result.get("status") == "finished":
                runtime_state["status"] = "finished"

        if result.get("ok") is False:
            # Keep authority-denied blocked shape from prior consolidation, but always
            # expose runtime_state for boundary-survival callers.
            error = result.get("error")
            error_type = error.get("type") if isinstance(error, dict) else ""
            text = " ".join(str(x or "") for x in (
                result.get("reason"),
                result.get("blocked_reason"),
                result.get("status"),
                error_type,
                error.get("reason") if isinstance(error, dict) else error,
            )).lower()
            if (
                error_type == "execution_authority_denied"
                or "runtime_execution_capability_not_validated" in text
                or "runtime_dispatcher_live_capability_required" in text
                or "execution_authority_denied" in text
            ):
                err = {
                    "type": "execution_authority_denied",
                    "reason": "runtime_execution_capability_not_validated",
                }
                result["status"] = "blocked"
                result["reason"] = "runtime_execution_capability_not_validated"
                result["blocked_reason"] = "runtime_execution_capability_not_validated"
                result["error"] = err
                runtime_state["status"] = "blocked"
                runtime_state.setdefault("blocked_reason", "runtime_execution_capability_not_validated")

                if isinstance(task, dict):
                    task["status"] = "blocked"
                    task["blocked_reason"] = "runtime_execution_capability_not_validated"
                    task["results"] = [{
                        "ok": False,
                        "status": "blocked",
                        "result": {"executed": False, "blocked": True},
                        "error": err,
                    }]
                    result["task"] = task

        result["runtime_state"] = runtime_state
        return result

    def _zero_stage3b_run_task_tick_v3(self, task, *args, **kwargs):
        result = _zero_stage3b_base_run_task_tick_v3(self, task, *args, **kwargs)
        return _zero_stage3b_normalize_taskrunner_result_v3(task, result)

    TaskRunner.run_task_tick = _zero_stage3b_run_task_tick_v3

    if hasattr(TaskRunner, "run_task"):
        _zero_stage3b_base_run_task_v3 = TaskRunner.run_task

        def _zero_stage3b_run_task_v3(self, task, *args, **kwargs):
            result = _zero_stage3b_base_run_task_v3(self, task, *args, **kwargs)
            return _zero_stage3b_normalize_taskrunner_result_v3(task, result)

        TaskRunner.run_task = _zero_stage3b_run_task_v3
except NameError:
    pass
'''

text = TARGET.read_text(encoding="utf-8")
if MARKER not in text:
    TARGET.write_text(text.rstrip() + "\n\n" + PATCH.strip() + "\n", encoding="utf-8")
    print("patched", TARGET)
else:
    print("already patched", TARGET)
