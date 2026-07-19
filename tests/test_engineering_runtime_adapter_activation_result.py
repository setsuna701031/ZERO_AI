from tests.runtime_adapter_activation_fixtures import *
def test_result():
 p=pipeline(); r=p['rs']; assert r['result_status']=='activated'; assert r['adapter_activation_state']=='governance_activated'; assert r['token_consumed'] is True
 for k in ['adapter_loaded','adapter_code_executed','adapter_invoked','runtime_invoked','executor_invoked','scheduler_invoked','authority_consumed','mutation_performed']: assert r[k] is False
 assert build_runtime_adapter_activation_result(dict(p['ca'],activation_status='not_activated'),p['tc'])['result_status']=='not_activated'
