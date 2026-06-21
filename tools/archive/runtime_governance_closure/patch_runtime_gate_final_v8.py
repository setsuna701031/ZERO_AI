from pathlib import Path

TASK_RUNNER = Path("core/runtime/task_runner.py")
SCHEDULER = Path("core/tasks/scheduler.py")

TASK_PATCH = r'''
# ZERO_PATCH_RUNTIME_GATE_FINAL_V8

def _zero_taskrunner_authority_denial_shape_v8(result, task):
    if not isinstance(result, dict) or result.get("ok") is not False:
        return result

    error = result.get("error")
    error_type = error.get("type") if isinstance(error, dict) else ""
    text = " ".join(str(x or "") for x in (
        result.get("reason"),
        result.get("blocked_reason"),
        result.get("status"),
        error_type,
        error.get("reason") if isinstance(error, dict) else error,
    )).lower()

    if not (
        error_type == "execution_authority_denied"
        or "runtime_execution_capability_not_validated" in text
        or "runtime_dispatcher_live_capability_required" in text
        or "execution_authority_denied" in text
    ):
        return result

    err = {
        "type": "execution_authority_denied",
        "reason": "runtime_execution_capability_not_validated",
    }

    result["ok"] = False
    result["status"] = "blocked"
    result["reason"] = "runtime_execution_capability_not_validated"
    result["blocked_reason"] = "runtime_execution_capability_not_validated"
    result["error"] = err

    target = task if isinstance(task, dict) else result.get("task")
    if isinstance(target, dict):
        target["status"] = "blocked"
        target["blocked_reason"] = "runtime_execution_capability_not_validated"

        target["results"] = [{
            "ok": False,
            "status": "blocked",
            "result": {
                "executed": False,
                "blocked": True,
            },
            "error": err,
        }]

        result["task"] = target

    return result

_zero_taskrunner_base_run_task_tick_v8 = TaskRunner.run_task_tick

def _zero_run_task_tick_v8(self, task, *args, **kwargs):
    return _zero_taskrunner_authority_denial_shape_v8(
        _zero_taskrunner_base_run_task_tick_v8(self, task, *args, **kwargs),
        task,
    )

TaskRunner.run_task_tick = _zero_run_task_tick_v8

if hasattr(TaskRunner, "run_task"):
    _zero_taskrunner_base_run_task_v8 = TaskRunner.run_task

    def _zero_run_task_v8(self, task, *args, **kwargs):
        return _zero_taskrunner_authority_denial_shape_v8(
            _zero_taskrunner_base_run_task_v8(self, task, *args, **kwargs),
            task,
        )

    TaskRunner.run_task = _zero_run_task_v8
'''

SCHED_PATCH = r'''
# ZERO_PATCH_SCHEDULER_OPERATOR_COMPLETION_V8

def _zero_scheduler_find_session_v8(obj, session_id, seen=None):
    if obj is None:
        return None
    if seen is None:
        seen = set()
    oid = id(obj)
    if oid in seen:
        return None
    seen.add(oid)

    get_session = getattr(obj, "get_session", None)
    if callable(get_session):
        try:
            session = get_session(session_id)
            if session is not None:
                return session
        except Exception:
            pass

    for attr in ("sessions", "_sessions", "operator_sessions", "_operator_sessions"):
        value = getattr(obj, attr, None)
        if isinstance(value, dict) and session_id in value:
            return value[session_id]

    for attr in ("operator_runtime", "runtime", "_runtime", "bridge", "_bridge", "operator_bridge"):
        found = _zero_scheduler_find_session_v8(getattr(obj, attr, None), session_id, seen)
        if found is not None:
            return found

    return None

def _zero_scheduler_record_complete_v8(self, task, result):
    if not isinstance(task, dict) or not isinstance(result, dict) or result.get("ok") is not True:
        return

    session_id = task.get("operator_session_id")
    if not session_id:
        return

    complete_id = f"{task.get('id') or task.get('task_id') or 'task'}-complete"

    roots = [
        getattr(self, "operator_bridge", None),
        getattr(getattr(self, "step_executor", None), "operator_bridge", None),
        getattr(self, "step_executor", None),
        self,
    ]

    for root in roots:
        session = _zero_scheduler_find_session_v8(root, session_id)
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

_zero_scheduler_base_run_one_step_v8 = Scheduler.run_one_step

def _zero_scheduler_run_one_step_v8(self, *args, **kwargs):
    result = _zero_scheduler_base_run_one_step_v8(self, *args, **kwargs)
    task = kwargs.get("task") if "task" in kwargs else (args[0] if args else None)

    if isinstance(result, dict) and result.get("ok") is True and isinstance(task, dict):
        try:
            current = int(task.get("current_step_index", task.get("step_index", 0)) or 0)
        except Exception:
            current = 0
        result.setdefault("current_step_index", current)
        result.setdefault("next_step_index", current + 1)
        task["current_step_index"] = result["next_step_index"]
        _zero_scheduler_record_complete_v8(self, task, result)

    return result

Scheduler.run_one_step = _zero_scheduler_run_one_step_v8
'''

def append_once(path, marker, patch):
    text = path.read_text(encoding="utf-8")
    if marker not in text:
        path.write_text(text.rstrip() + "\n\n" + patch.strip() + "\n", encoding="utf-8")
        print("patched", path)
    else:
        print("already patched", path)

append_once(TASK_RUNNER, "ZERO_PATCH_RUNTIME_GATE_FINAL_V8", TASK_PATCH)
append_once(SCHEDULER, "ZERO_PATCH_SCHEDULER_OPERATOR_COMPLETION_V8", SCHED_PATCH)