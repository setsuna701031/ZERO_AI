from core.engineering.engineering_task_orchestration_closure import build_task_closure

def test_closure_deterministic():
    s={'task_id':'t','repository_identity':{'id':'r'},'request_identity':{'id':'q'},'completed_phases':['verified']}
    assert build_task_closure(s)==build_task_closure(dict(reversed(list(s.items()))))
