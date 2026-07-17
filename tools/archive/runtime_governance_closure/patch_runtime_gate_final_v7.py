from pathlib import Path

TASK_RUNNER = Path("core/runtime/task_runner.py")
SCHEDULER = Path("core/tasks/scheduler.py")

TASK_PATCH = r'''
# ZERO_PATCH_RUNTIME_GATE_FINAL_V7

_zero_taskrunner_base_run_task_tick_v7 = TaskRunner.run_task_tick

def _zero_run_task_tick_v7(self, task, *args, **kwargs):
    result = _zero_taskrunner_base_run_task_tick_v7(self, task, *args, **kwargs)

    if isinstance(result, dict) and result.get("ok") is False:
        error = result.get("error")
        error_type = error.get("type") if isinstance(error, dict) else ""
        text = " ".join(str(x or "") for x in (
            result.get("reason"),
            result.get("blocked_reason"),
            result.get("status"),
            error_type,
            error if isinstance(error, str) else "",
        )).lower()

        if (
            error_type == "execution_authority_denied"
            or "runtime_execution_capability_not_validated" in text
            or "runtime_dispatcher_live_capability_required" in text
        ):
            result["status"] = "blocked"
            result["reason"] = "runtime_execution_capability_not_validated"
            result["blocked_reason"] = "runtime_execution_capability_not_validated"
            result["error"] = {
                "type": "execution_authority_denied",
                "reason": "runtime_execution_capability_not_validated",
            }

            target_task = task if isinstance(task, dict) else result.get("task")
            if isinstance(target_task, dict):
                target_task["status"] = "blocked"
                target_task["blocked_reason"] = "runtime_execution_capability_not_validated"

                results = target_task.get("results")
                if not isinstance(results, list) or not results:
                    results = [{"ok": False, "status": "blocked", "result": {}}]

                first = results[0]
                if not isinstance(first, dict):
                    first = {"ok": False, "status": "blocked", "result": {}}
                    results[0] = first

                first["ok"] = False
                first["status"] = "blocked"

                inner = first.get("result")
                if not isinstance(inner, dict):
                    inner = {}
                    first["result"] = inner

                inner["executed"] = False
                inner["blocked"] = True
                first["error"] = result["error"]

                target_task["results"] = results
                result["task"] = target_task

    return result

TaskRunner.run_task_tick = _zero_run_task_tick_v7

if hasattr(TaskRunner, "run_task"):
    _zero_taskrunner_base_run_task_v7 = TaskRunner.run_task

    def _zero_run_task_v7(self, task, *args, **kwargs):
        result = _zero_taskrunner_base_run_task_v7(self, task, *args, **kwargs)
        if isinstance(result, dict) and isinstance(task, dict):
            result["task"] = task
        return result

    TaskRunner.run_task = _zero_run_task_v7
'''

SCHED_PATCH = r'''
# ZERO_PATCH_SCHEDULER_OPERATOR_SESSION_COMPLETION_V7

def _zero_scheduler_record_operator_completion_v7(self, task, result):
    if not isinstance(task, dict) or not isinstance(result, dict):
        return
    if result.get("ok") is not True:
        return

    session_id = task.get("operator_session_id")
    if not session_id:
        return

    task_id = str(task.get("id") or task.get("task_id") or "task")
    complete_id = f"{task_id}-complete"

    bridge = getattr(getattr(self, "step_executor", None), "operator_bridge", None) or getattr(self, "operator_bridge", None)
    candidates = [
        getattr(bridge, "operator_runtime", None),
        getattr(bridge, "runtime", None),
        getattr(bridge, "_runtime", None),
        bridge,
    ]

    for runtime in candidates:
        if runtime is None:
            continue

        session = None
        get_session = getattr(runtime, "get_session", None)
        if callable(get_session):
            try:
                session = get_session(session_id)
            except Exception:
                session = None

        if session is None:
            sessions = getattr(runtime, "sessions", None) or getattr(runtime, "_sessions", None)
            if isinstance(sessions, dict):
                session = sessions.get(session_id)

        if session is None:
            continue

        completed = getattr(session, "completed_steps", None)
        if isinstance(completed, list):
            if complete_id not in completed:
                completed.append(complete_id)
            return

        if isinstance(session, dict):
            completed = session.setdefault("completed_steps", [])
            if isinstance(completed, list) and complete_id not in completed:
                completed.append(complete_id)
            return

_zero_scheduler_base_run_one_step_v7 = Scheduler.run_one_step

def _zero_scheduler_run_one_step_v7(self, *args, **kwargs):
    result = _zero_scheduler_base_run_one_step_v7(self, *args, **kwargs)
    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)

    if isinstance(result, dict) and result.get("ok") is True and isinstance(task, dict):
        result.setdefault("current_step_index", int(task.get("current_step_index", task.get("step_index", 0)) or 0))
        result.setdefault("next_step_index", result["current_step_index"] + 1)
        task["current_step_index"] = result["next_step_index"]
        _zero_scheduler_record_operator_completion_v7(self, task, result)

    return result

Scheduler.run_one_step = _zero_scheduler_run_one_step_v7
'''

def append_once(path, marker, patch):
    text = path.read_text(encoding="utf-8")
    if marker not in text:
        path.write_text(text.rstrip() + "\n\n" + patch.strip() + "\n", encoding="utf-8")
        print("patched", path)
    else:
        print("already patched", path)

append_once(TASK_RUNNER, "ZERO_PATCH_RUNTIME_GATE_FINAL_V7", TASK_PATCH)
append_once(SCHEDULER, "ZERO_PATCH_SCHEDULER_OPERATOR_SESSION_COMPLETION_V7", SCHED_PATCH)