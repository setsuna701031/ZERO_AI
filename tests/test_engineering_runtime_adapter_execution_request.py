from tests.runtime_adapter_execution_integration_fixtures import *
def test_request_linkage_and_determinism():
 a=build_runtime_adapter_execution_request(invocation_handoff(),invocation_closure()); b=build_runtime_adapter_execution_request(invocation_handoff(),invocation_closure())
 assert a==b and a['request_status']=='accepted' and validate_runtime_adapter_execution_request(a).valid
 assert a['invocation_handoff_id']=='rth-x' and a['upstream_closure_fingerprint']=='closure-fp'
def test_request_rejects_bad_handoff():
 h=invocation_handoff(); h['real_execution_authorized']=True
 assert build_runtime_adapter_execution_request(h,invocation_closure())['request_status']=='invalid'
