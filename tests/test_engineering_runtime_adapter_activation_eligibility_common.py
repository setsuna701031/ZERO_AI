from core.engineering.engineering_runtime_adapter_activation_eligibility_common import *
def test_determinism_and_canonical_ordering():
 a={'b':2,'a':1}; b={'a':1,'b':2}; assert canonical_json(a)==canonical_json(b); assert canonical_fingerprint(a)==canonical_fingerprint(b); assert normalize_reasons(['b','a','a'])==['a','b']
def test_scope_and_payload_rejection():
 assert scope_bounded({'x':['a']},{'x':['a','b']}); assert not scope_bounded(['*'],['a']); assert contains_prohibited({'command':'x'}); assert contains_credential_like({'api_key':'x'})
def test_bounds_and_authority():
 scope={'x':['a']}; auth={'non_transferable':True,'non_reusable':True,'scope_bound':True,'perpetual':False,'passive':True,'consumed':False,'closed':False,'unrestricted':False,'restricted':True,'scope':scope}
 assert resources_valid({'n':1}); assert not resources_valid({'n':0}); assert timeout_valid({'seconds':1,'finite':True,'perpetual':False}); assert not timeout_valid({'seconds':float('inf'),'finite':True,'perpetual':False}); assert environment_valid({'network':'disabled'}); assert authority_valid(auth,scope)
