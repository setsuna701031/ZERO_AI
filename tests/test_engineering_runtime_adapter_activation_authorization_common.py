from core.engineering.engineering_runtime_adapter_activation_authorization_common import *
def test_determinism_and_canonical_json():
 a={'b':1,'a':2}; assert canonical_fingerprint(a)==canonical_fingerprint({'a':2,'b':1}); assert canonical_json(a)=='{"a":2,"b":1}'
def test_prohibited_payloads_and_bounds():
 for k in ['command','shell','script','source_code','executable','binary','module_path','callback','entrypoint','patch','activation_command','credentials','api_key','private_key','bearer','environment_secrets','activation_token','token_value','authorization_header']:
  assert contains_prohibited({k:'x'})
 assert not contains_prohibited({'authority_reference':'authority:opaque:1','token_request_id':'request:opaque:1'})
 assert scope_bounded({'x':['a']},{'x':['a','b']}) and not scope_bounded({'x':['c']},{'x':['a']})
 assert resources_valid({'cpu':1}) and not resources_valid({'cpu':0}) and not resources_valid({'cpu':'1'})
 assert timeout_valid({'seconds':1,'finite':True,'perpetual':False}) and not timeout_valid({'seconds':0,'finite':True,'perpetual':False})
