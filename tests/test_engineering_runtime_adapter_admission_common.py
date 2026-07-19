from core.engineering.engineering_runtime_adapter_admission_common import *
def test_deterministic_fingerprint_identity_and_json():
 v={'b':2,'a':1}; assert canonical_json(v)=='{"a":1,"b":2}'; assert canonical_fingerprint(v)==canonical_fingerprint({'a':1,'b':2}); assert canonical_identity('p-',v)==canonical_identity('p-',{'a':1,'b':2})
def test_reject_wildcard_and_payloads():
 assert contains_wildcard({'scope':['*']}); assert contains_prohibited({'token':'x'}); assert authority_valid({'non_transferable':True,'non_reusable':True,'scope_bound':True,'perpetual':False,'passive':True,'consumed':False,'closed':False,'unrestricted':False,'scope':{'files':['a']}},{'files':['a','b']})
