from __future__ import annotations
from .engineering_task_orchestration_persistence import load_state, save_state

def resume_task(repo_root, task_id):
    state=load_state(repo_root, task_id)
    if state.get('execution_started') and not state.get('execution_completed'):
        state=dict(state); state['lifecycle_state']='blocked'; state['pending_requirement']='execution_recovery_required'; state['failure']={'code':'ambiguous_execution_state'}; state['terminal']=True
        from .engineering_task_orchestration import seal_state
        return save_state(repo_root, seal_state(state))
    return state
