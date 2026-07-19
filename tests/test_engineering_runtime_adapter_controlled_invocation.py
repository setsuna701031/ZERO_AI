from tests.runtime_adapter_invocation_fixtures import *

def test_pipeline_deterministic_and_valid():
 first=pipeline(); second=pipeline(); assert first['cl']==second['cl']; assert first['cl']['package_status']=='closed'

def test_rejects_prohibited_and_scope_expansion():
 bad=request(scope=['scope.alpha','scope.beta']); assert not validate_runtime_adapter_invocation_intake_request(bad).valid
 bad2=request(input_bindings={'command':'run'}); assert not validate_runtime_adapter_invocation_intake_request(bad2).valid
