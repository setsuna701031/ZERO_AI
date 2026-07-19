from tests.runtime_adapter_activation_authorization_fixtures import chain_auth
from core.engineering.engineering_runtime_adapter_activation_authorization_handoff import *
def test_handoff_from_authorized_decision():
 *_,auth,hand,clo=chain_auth(); assert hand['eligible_for_activation_token_review'] is True; assert hand['activation_authorized'] is True; assert validate_runtime_adapter_activation_authorization_handoff(hand).valid
 for k in ['activation_token_issued','token_material_present','adapter_loaded','adapter_activated','adapter_invoked','runtime_invoked','authority_consumed','mutation_performed']: assert hand[k] is False
def test_handoff_rejected_from_invalid_decision_and_linkage():
 *_,auth,hand,clo=chain_auth(); bad=dict(auth); bad['authorization_status']='invalid'; h=build_runtime_adapter_activation_authorization_handoff(bad); assert h['eligible_for_activation_token_review'] is False; assert validate_runtime_adapter_activation_authorization_handoff(h).valid
 bad=dict(hand); bad['activation_token_issued']=True; assert not validate_runtime_adapter_activation_authorization_handoff(bad).valid
