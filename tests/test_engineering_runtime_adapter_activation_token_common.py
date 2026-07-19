from core.engineering.engineering_runtime_adapter_activation_token_common import *

def test_common_determinism_and_payload_rejection():
    a={'b':1,'a':[2]}; assert canonical_json(a)=='{"a":[2],"b":1}'
    assert canonical_fingerprint(a)==canonical_fingerprint({'a':[2],'b':1})
    assert normalize_reasons(['b','a','a'])==['a','b']
    for key in ['command','shell','script','source_code','executable','binary','module_path','callback','entrypoint','patch','credentials','password','private_key','api_key','bearer_token','access_token','refresh_token','authorization_header','environment_secrets','raw_token','token_value','token_secret']:
        assert contains_prohibited({key:'x'})
    assert not contains_prohibited({'token_id':'token-identifier-only','authority_reference':'authority:id','executable':False})

def test_common_scope_and_constraints():
    scope={'operations':['observe','audit']}
    assert scope_bounded({'operations':['observe']},scope)
    assert not scope_bounded({'operations':['observe','run']},scope)
    assert not scope_bounded('*',scope)
