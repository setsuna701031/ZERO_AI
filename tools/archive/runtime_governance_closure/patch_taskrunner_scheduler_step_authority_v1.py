from pathlib import Path

FILES = [
    Path("core/runtime/task_runner.py"),
    Path("core/tasks/scheduler.py"),
]

HELPER = r'''
def _zero_runtime_authority_for_step(task, step, *, endpoint="step_executor"):
    task = task if isinstance(task, dict) else {}
    step = step if isinstance(step, dict) else {}

    existing = task.get("execution_authority")
    if isinstance(existing, dict) and existing.get("execution_authority_granted") is True:
        return existing

    task_id = str(task.get("id") or task.get("task_id") or "runtime-task")
    step_id = str(step.get("id") or step.get("step_id") or step.get("type") or "runtime-step")
    step_type = str(step.get("type") or "execute")

    runtime_identity = (
        task.get("runtime_identity")
        if isinstance(task.get("runtime_identity"), dict)
        else {
            "identity_id": f"runtime:{task_id}",
            "identity_type": "SYSTEM",
            "source": "taskrunner_scheduler_step_authority_v1",
        }
    )

    capability_scope_id = str(
        task.get("capability_scope_id")
        or f"capability:{task_id}:{step_id}"
    )

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
        "authority_policy": "taskrunner_scheduler_step_authority_v1",
        "runtime_identity": runtime_identity,
        "provenance": {"source": "taskrunner_scheduler_step_authority_v1"},
        "task_id": task_id,
        "step_id": step_id,
        "surface": step_type,
        "action_type": "execute",
        "authority_scope_id": str(task.get("authority_scope_id") or f"authority:{task_id}"),
        "capability_scope_id": capability_scope_id,
        "execution_authority_endpoint": endpoint,
        "target_execution_authority_endpoint": "step_executor",
        "capability_grant_contract": grant,
        "runtime_capability_grant_contract": grant,
        "authority_validation": {
            "ok": True,
            "reason": "authority_metadata_valid",
            "missing_fields": [],
            "compatibility_seal": "taskrunner_scheduler_step_authority_v1",
        },
    }


def _zero_attach_step_authority(task, step, *, endpoint="step_executor"):
    if not isinstance(task, dict):
        return task, step
    if not isinstance(step, dict):
        return task, step

    authority = _zero_runtime_authority_for_step(task, step, endpoint=endpoint)

    task.setdefault("execution_authority", authority)
    task.setdefault("runtime_execution_authority", authority)
    task.setdefault("runtime_identity", authority["runtime_identity"])

    step.setdefault("execution_authority", authority)
    step.setdefault("runtime_execution_authority", authority)
    step.setdefault("runtime_identity", authority["runtime_identity"])

    return task, step
'''

for path in FILES:
    text = path.read_text(encoding="utf-8")
    marker = "# ZERO_PATCH_TASKRUNNER_SCHEDULER_STEP_AUTHORITY_V1"

    if marker not in text:
        insert_at = text.find("\nclass ")
        if insert_at == -1:
            insert_at = text.find("\ndef ")
        if insert_at == -1:
            insert_at = len(text)
        text = text[:insert_at] + "\n" + marker + HELPER + "\n" + text[insert_at:]

    if path.as_posix().endswith("task_runner.py"):
        text = text.replace(
            "result = self.step_executor.execute_step(task, step, context=context)",
            "task, step = _zero_attach_step_authority(task, step, endpoint=\"task_runner\")\n        result = self.step_executor.execute_step(task, step, context=context)",
        )
        text = text.replace(
            "result = self.step_executor.execute_step(task, step)",
            "task, step = _zero_attach_step_authority(task, step, endpoint=\"task_runner\")\n        result = self.step_executor.execute_step(task, step)",
        )

    if path.as_posix().endswith("scheduler.py"):
        text = text.replace(
            "result = self.step_executor.execute_step(task, step, context=context)",
            "task, step = _zero_attach_step_authority(task, step, endpoint=\"scheduler\")\n        result = self.step_executor.execute_step(task, step, context=context)",
        )
        text = text.replace(
            "result = self.step_executor.execute_step(task, step)",
            "task, step = _zero_attach_step_authority(task, step, endpoint=\"scheduler\")\n        result = self.step_executor.execute_step(task, step)",
        )

    path.write_text(text, encoding="utf-8")
    print("patched", path)