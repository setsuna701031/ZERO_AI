from core.engineering.engineering_runtime_adapter_preparation_common import *
def test_determinism_and_prohibitions():
 a={'b':1,'a':[2]}; assert canonical_fingerprint(a)==canonical_fingerprint({'a':[2],'b':1}); assert canonical_identity('p-',a)==canonical_identity('p-',a)
 for k in ('command','shell','script','source_code','executable','module_path','callable','patch','diff','api_key','private_key','bearer','environment_secrets'):
  assert contains_prohibited({k:'x'})
 assert not contains_prohibited({'authority_reference':'opaque-token-identity'})
def test_bounds():
 assert scope_bounded({'files':['a']},{'files':['a','b']}); assert not scope_bounded({'files':['*']},{'files':['a']})
 assert resources_valid({'cpu':1}); assert not resources_valid({'cpu':0}); assert timeout_valid({'seconds':1,'finite':True,'perpetual':False}); assert not timeout_valid({'seconds':0,'finite':True,'perpetual':False})
