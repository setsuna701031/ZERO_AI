from __future__ import annotations

from pathlib import Path

TARGET = Path('core/runtime/task_runner.py')
MARKER = '# STAGE3B_TASKRUNNER_VERIFICATION_FIX'

PATCH = r'''
# STAGE3B_TASKRUNNER_VERIFICATION_FIX
# Consolidation follow-up for Stage 3B.
# Keeps the formal TaskRunner behavior expected by runtime-mode and boundary
# survival contracts after the temporary ZERO_PATCH gate wrappers were removed.

def _stage3b_taskrunner_enrich_success_result(result, task):
    if not isinstance(result, dict):
        return result

    if result.get("ok") is True:
        # TaskRunner terminal contract uses "finished"; StepExecutor simple handler
        # results often use "completed". Normalize only at TaskRunner boundary.
        if result.get("status") == "completed":
            result["status"] = "finished"

        runtime_state = result.get("runtime_state")
        if not isinstance(runtime_state, dict):
            runtime_state = {}
            result["runtime_state"] = runtime_state

        if isinstance(task, dict):
            if task.get("operator_session_id"):
                runtime_state.setdefault("operator_session_id", task.get("operator_session_id"))
            if task.get("runtime_session_id"):
                runtime_state.setdefault("runtime_session_id", task.get("runtime_session_id"))
            if task.get("task_id") or task.get("id"):
                runtime_state.setdefault("task_id", task.get("task_id") or task.get("id"))

    return result

_stage3b_taskrunner_base_run_task_tick = TaskRunner.run_task_tick

def _stage3b_run_task_tick(self, task, *args, **kwargs):
    result = _stage3b_taskrunner_base_run_task_tick(self, task, *args, **kwargs)
    return _stage3b_taskrunner_enrich_success_result(result, task)

TaskRunner.run_task_tick = _stage3b_run_task_tick

if hasattr(TaskRunner, "run_task"):
    _stage3b_taskrunner_base_run_task = TaskRunner.run_task

    def _stage3b_run_task(self, task, *args, **kwargs):
        result = _stage3b_taskrunner_base_run_task(self, task, *args, **kwargs)
        return _stage3b_taskrunner_enrich_success_result(result, task)

    TaskRunner.run_task = _stage3b_run_task
'''


def main() -> None:
    text = TARGET.read_text(encoding='utf-8')
    if MARKER not in text:
        TARGET.write_text(text.rstrip() + '\n\n' + PATCH.strip() + '\n', encoding='utf-8')
        print('patched', TARGET)
    else:
        print('already patched', TARGET)


if __name__ == '__main__':
    main()
