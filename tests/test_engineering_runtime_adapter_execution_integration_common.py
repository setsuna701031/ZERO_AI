from core.engineering.engineering_runtime_adapter_execution_integration_common import *
def test_common_deterministic_fingerprint_and_guards():
 assert canonical_fingerprint({'b':2,'a':1})==canonical_fingerprint({'a':1,'b':2})
 assert contains_prohibited({'command':'run'})
 assert contains_prohibited({'password':'x'})
 assert scope_subset(['a'],['a','b'])
 assert not scope_subset(['a','c'],['a','b'])
 assert strict_int(1,1,2) and not strict_int('1',1,2) and not strict_int(-1,0,2)
