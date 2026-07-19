from tests.runtime_adapter_activation_fixtures import *
def test_handoff():
 p=pipeline(); h=p['ho']; assert h['eligible_for_invocation_governance'] is True; assert h['activation_governance_completed'] is True; assert h['token_consumed'] is True
 for k in ['adapter_loaded','adapter_code_executed','adapter_invoked','runtime_invoked','authority_consumed','mutation_performed']: assert h[k] is False
 assert build_runtime_adapter_activation_handoff(p['rs'],dict(p['vf'],verification_status='not_verified'))['eligible_for_invocation_governance'] is False
