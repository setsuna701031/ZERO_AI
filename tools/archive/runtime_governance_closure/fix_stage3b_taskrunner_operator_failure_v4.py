from pathlib import Path

TARGET = Path('core/runtime/task_runner.py')
MARKER = 'ZERO_STAGE3B_TASKRUNNER_OPERATOR_FAILURE_V4'
PATCH = r'''
# ZERO_STAGE3B_TASKRUNNER_OPERATOR_FAILURE_V4
# Consolidation fix: after Stage 3B removed runtime gate patch wrappers, TaskRunner
# must still publish operator failure state for run_task_tick failure paths.

_ZERO_STAGE3B_BASE_RUN_TASK_TICK_V4 = TaskRunner.run_task_tick

def _zero_stage3b_taskrunner_record_operator_failure_v4(task, result):
    if not isinstance(task, dict) or not isinstance(result, dict):
        return result

    session_id = task.get('operator_session_id')
    if not session_id:
        runtime_state = result.get('runtime_state')
        if isinstance(runtime_state, dict):
            session_id = runtime_state.get('operator_session_id')
    if not session_id:
        return result

    runtime_state = result.setdefault('runtime_state', {})
    if isinstance(runtime_state, dict):
        runtime_state.setdefault('operator_session_id', session_id)

    if result.get('ok') is False:
        import builtins
        failures = getattr(builtins, '_zero_operator_failure_registry_v14', None)
        if not isinstance(failures, dict):
            failures = {}
            setattr(builtins, '_zero_operator_failure_registry_v14', failures)
        task_id = str(task.get('id') or task.get('task_id') or 'task')
        failures[str(session_id)] = f'{task_id}-fail'

        # Keep the public result shape stable for boundary-survival tests.
        result.setdefault('status', 'blocked' if result.get('blocked_reason') else 'failed')
        result.setdefault('blocked_reason', result.get('reason') or result.get('error') or '')

    return result

def _zero_stage3b_run_task_tick_v4(self, task, *args, **kwargs):
    result = _ZERO_STAGE3B_BASE_RUN_TASK_TICK_V4(self, task, *args, **kwargs)
    return _zero_stage3b_taskrunner_record_operator_failure_v4(task, result)

TaskRunner.run_task_tick = _zero_stage3b_run_task_tick_v4

if hasattr(TaskRunner, 'run_task'):
    _ZERO_STAGE3B_BASE_RUN_TASK_V4 = TaskRunner.run_task

    def _zero_stage3b_run_task_v4(self, task, *args, **kwargs):
        result = _ZERO_STAGE3B_BASE_RUN_TASK_V4(self, task, *args, **kwargs)
        return _zero_stage3b_taskrunner_record_operator_failure_v4(task, result)

    TaskRunner.run_task = _zero_stage3b_run_task_v4
'''

text = TARGET.read_text(encoding='utf-8')
if MARKER not in text:
    TARGET.write_text(text.rstrip() + '\n\n' + PATCH.strip() + '\n', encoding='utf-8')
    print('patched', TARGET)
else:
    print('already patched', TARGET)
