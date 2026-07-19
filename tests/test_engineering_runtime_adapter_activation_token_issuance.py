from copy import deepcopy
from tests.runtime_adapter_activation_token_fixtures import chain_token, eligibility_request, CONSTRAINTS
from core.engineering.engineering_runtime_adapter_activation_token_eligibility import validate_runtime_adapter_activation_token_eligibility_request
from core.engineering.engineering_runtime_adapter_activation_token_issuance import *

def test_issuance_valid_deterministic_and_safe():
    chain1=chain_token(); chain2=chain_token(); assert chain1==chain2
    req,elig,ppol,prep,rr,rev,apol,auth,iss,ver,hof,clo=chain1
    assert iss['token_id'].startswith('engineering-runtime-adapter-activation-token-')
    assert 'token_value' not in iss and iss.get('token_is_secret') is False and iss.get('bearer_credential') is False
    assert not iss['adapter_loaded'] and not iss['adapter_activated'] and not iss['adapter_invoked'] and not iss['runtime_invoked'] and not iss['authority_consumed'] and not iss['mutation_performed']
    assert clo['package_status']=='closed'

def test_issuance_invalid_payload_and_bounds():
    req,elig,ppol,prep,rr,rev,apol,auth,iss,ver,hof,clo=chain_token()
    bad=deepcopy(req); bad['requested_max_uses']=2
    chain=chain_token(bad); assert chain[1]['eligibility_status']!='eligible'
    bad=deepcopy(req); bad['requested_token_scope']={'operations':['observe','expand']}
    chain=chain_token(bad); assert chain[1]['eligibility_status']!='eligible'
    bad=deepcopy(CONSTRAINTS); bad['token_value']='secret'
    req2,_,_=eligibility_request(token_constraints=bad); assert validate_runtime_adapter_activation_token_eligibility_request(req2).valid is False
