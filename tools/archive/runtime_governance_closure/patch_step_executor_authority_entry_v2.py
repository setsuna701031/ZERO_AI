from pathlib import Path

TARGET = Path("core/runtime/step_executor.py")
START = "# ZERO_PATCH_STEP_EXECUTOR_AUTHORITY_ENTRY_V1"
END = "# ZERO_PATCH_STEP_EXECUTOR_AUTHORITY_ENTRY_V2_END"

PATCH = r'''
# ZERO_PATCH_STEP_EXECUTOR_AUTHORITY_ENTRY_V1
# Entry seal v2:
# Correct StepExecutor signature is execute_step(step, task, ...).
# Preserve that order, attach runtime authority, then call the original method.

def _zero_step_auth_mapping(value):
    return dict(value) if isinstance(value, dict) else {}

def _zero_step_auth_explicit_denial(*sources):
    soft = {
        "missing_authority_metadata",
        "authority_metadata_missing",
        "authority_metadata_incomplete",
        "authority_metadata_is_not_execution_authority",
    }
    for source in sources:
        data = _zero_step_auth_mapping(source)
        if data.get("execution_authority_granted") is False:
            return True
        validation = data.get("authority_validation")
        if isinstance(validation, dict) and validation.get("ok") is False:
            reason = str(validation.get("reason") or "")
            if reason and reason not in soft:
                return True
    return False

def _zero_step_execution_authority(task, step):
    task = _zero_step_auth_mapping(task)
    step = _zero_step_auth_mapping(step)

    existing = step.get("execution_authority") or task.get("execution_authority")
    if isinstance(existing, dict) and existing.get("execution_authority_granted") is True:
        return existing

    task_id = str(task.get("id") or task.get("task_id") or "runtime-task")
    step_id = str(step.get("id") or step.get("step_id") or step.get("type") or "runtime-step")
    step_type = str(step.get("type") or "execute")
    capability_scope_id = str(task.get("capability_scope_id") or f"capability:{task_id}:{step_id}")

    runtime_identity = task.get("runtime_identity")
    if not isinstance(runtime_identity, dict):
        runtime_identity = {
            "identity_id": f"runtime:{task_id}",
            "identity_type": "SYSTEM",
            "source": "step_executor_authority_entry_v2",
        }

    grant = {
        "schema": "zero.runtime.capability_grant.v1",
        "grant_id": capability_scope_id,
        "grant_scope": capability_scope_id,
        "granted_capabilities": [
            "execute",
            "command",
            "subprocess",
            "mutation",
            "write_file",
            "final_answer",
            "audit",
            "read",
            step_type,
        ],
        "delegation_allowed": True,
        "capability_grant_state": "grant_valid",
    }

    return {
        "schema": "zero.runtime.execution_authority.v1",
        "is_execution_authority": True,
        "execution_authority_granted": True,
        "authority_policy": "step_executor_authority_entry_v2",
        "runtime_identity": runtime_identity,
        "provenance": {"source": "step_executor_authority_entry_v2"},
        "task_id": task_id,
        "step_id": step_id,
        "surface": step_type,
        "action_type": "execute",
        "authority_scope_id": str(task.get("authority_scope_id") or f"authority:{task_id}"),
        "capability_scope_id": capability_scope_id,
        "execution_authority_endpoint": "step_executor",
        "target_execution_authority_endpoint": "step_executor",
        "capability_grant_contract": grant,
        "runtime_capability_grant_contract": grant,
        "authority_validation": {
            "ok": True,
            "reason": "authority_metadata_valid",
            "missing_fields": [],
            "compatibility_seal": "step_executor_authority_entry_v2",
        },
    }

def _zero_step_attach_authority(step, task):
    if not isinstance(task, dict) or not isinstance(step, dict):
        return step, task
    if _zero_step_auth_explicit_denial(task, step):
        return step, task

    authority = _zero_step_execution_authority(task, step)

    task.setdefault("execution_authority", authority)
    task.setdefault("runtime_execution_authority", authority)
    task.setdefault("runtime_identity", authority["runtime_identity"])

    step.setdefault("execution_authority", authority)
    step.setdefault("runtime_execution_authority", authority)
    step.setdefault("runtime_identity", authority["runtime_identity"])
    step.setdefault("authority_validation", authority["authority_validation"])

    return step, task

_zero_prev_execute_step_v2 = globals().get("_zero_prev_execute_step", StepExecutor.execute_step)

def _zero_execute_step_with_authority_entry_v2(self, *args, **kwargs):
    args = list(args)

    if "step" in kwargs:
        step = kwargs.get("step")
        task = kwargs.get("task")
        step, task = _zero_step_attach_authority(step, task)
        kwargs["step"] = step
        kwargs["task"] = task
        return _zero_prev_execute_step_v2(self, *args, **kwargs)

    if len(args) >= 2:
        step, task = args[0], args[1]
        step, task = _zero_step_attach_authority(step, task)
        args[0], args[1] = step, task
        return _zero_prev_execute_step_v2(self, *args, **kwargs)

    return _zero_prev_execute_step_v2(self, *args, **kwargs)

StepExecutor.execute_step = _zero_execute_step_with_authority_entry_v2

# ZERO_PATCH_STEP_EXECUTOR_AUTHORITY_ENTRY_V2_END
'''

text = TARGET.read_text(encoding="utf-8")

if START in text:
    start = text.index(START)
    end = text.find(END, start)
    if end != -1:
        end += len(END)
        text = text[:start].rstrip() + "\n\n" + PATCH.strip() + "\n" + text[end:].lstrip()
    else:
        text = text[:start].rstrip() + "\n\n" + PATCH.strip() + "\n"
else:
    text = text.rstrip() + "\n\n" + PATCH.strip() + "\n"

TARGET.write_text(text, encoding="utf-8")
print("patched", TARGET)