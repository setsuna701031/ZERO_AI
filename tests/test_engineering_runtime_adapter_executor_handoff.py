from tests.runtime_adapter_execution_integration_fixtures import *
def test_executor_handoff_passive_and_rejects_true_flags():
 p=pipeline(); assert p['hand']['handoff_status']=='handed_off' and validate_runtime_adapter_executor_handoff(p['hand']).valid
 h=dict(p['hand']); h['executor_invoked']=True
 assert not validate_runtime_adapter_executor_handoff(h).valid
