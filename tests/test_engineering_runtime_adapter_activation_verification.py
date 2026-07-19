from tests.runtime_adapter_activation_fixtures import *
def test_verification():
 p=pipeline(); v=p['vf']; assert v['verification_status']=='verified'; assert v['identity_valid'] and v['linkage_valid'] and v['usage_transition_valid'] and v['token_state_transition_valid'] and v['non_execution_invariants_valid']
 assert verify_runtime_adapter_activation_boundary(p['ad'],p['pr'],dict(p['ca'],adapter_loaded=True),p['tc'],p['rs'])['verification_status']=='not_verified'
 assert verify_runtime_adapter_activation_boundary(p['ad'],p['pr'],p['ca'],dict(p['tc'],current_uses=2),p['rs'])['verification_status']=='not_verified'
