import json, pytest
from core.engineering.engineering_task_orchestration import create_task
from core.engineering.engineering_task_orchestration_persistence import load_state, state_path, TaskPersistenceError

def test_persistence_reload_and_corruption(tmp_path):
    s=create_task(tmp_path, {'repository_identity':{'id':'r'},'requested_outcome':'x'})
    assert load_state(tmp_path,s['task_id'])==s
    p=state_path(tmp_path,s['task_id']); data=json.loads(p.read_text()); data['lifecycle_state']='admitted'; p.write_text(json.dumps(data))
    with pytest.raises(TaskPersistenceError): load_state(tmp_path,s['task_id'])
    p.write_text('{')
    with pytest.raises(TaskPersistenceError): load_state(tmp_path,s['task_id'])
