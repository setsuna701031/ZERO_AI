from core.engineering.engineering_task_orchestration import create_task, seal_state
from core.engineering.engineering_task_orchestration_persistence import save_state
from core.engineering.engineering_task_orchestration_resume import resume_task

def test_ambiguous_execution_blocks(tmp_path):
    s=create_task(tmp_path, {'repository_identity':{'id':'r'},'requested_outcome':'x'})
    s=dict(s); s['lifecycle_state']='executing'; s['execution_started']=True; s['execution_completed']=False
    save_state(tmp_path, seal_state(s))
    r=resume_task(tmp_path,s['task_id'])
    assert r['lifecycle_state']=='blocked' and r['pending_requirement']=='execution_recovery_required'
