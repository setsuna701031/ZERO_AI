from tests.runtime_adapter_activation_authorization_fixtures import chain_auth
from core.engineering.engineering_runtime_adapter_activation_authorization_closure import *
def test_closure_mapping_and_prohibitions():
 *_,clo=chain_auth(); assert clo['package_status']=='closed'; assert validate_runtime_adapter_activation_authorization_closure(clo).valid
 for k in ['activation_token_prohibited','token_material_prohibited','adapter_loading_prohibited','adapter_activation_prohibited','adapter_invocation_prohibited','runtime_invocation_prohibited','authority_consumption_prohibited','mutation_prohibited']: assert clo[k] is True
def test_closure_invalid_mapping():
 req,pol,rev,auth,hand,clo=chain_auth(); bad=dict(hand); bad['activation_token_issued']=True; c=build_runtime_adapter_activation_authorization_closure(req,pol,rev,auth,bad); assert c['package_status']=='invalid'
