from tests.runtime_adapter_activation_fixtures import *
def test_consumption_transition():
 p=pipeline(); t=p['tc']; assert t['consumption_status']=='consumed'; assert (t['max_uses'],t['previous_uses'],t['current_uses'])==(1,0,1); assert t['token_state_before']=='issued_unconsumed' and t['token_state_after']=='consumed'
 for k in ['secret_material_consumed','external_credential_consumed','authority_consumed','mutation_performed']: assert t[k] is False
 assert build_runtime_adapter_activation_token_consumption(dict(p['ca'],activation_status='not_activated'))['consumption_status']=='not_consumed'
