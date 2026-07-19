from tests.runtime_adapter_execution_integration_fixtures import *
def test_environment_admission_invalid_network():
 p=pipeline(); assert p['env']['admission_status']=='admitted'
 assert build_runtime_adapter_execution_environment_admission(environment_profile={'network_mode':'enabled','logical_cpu_count':1,'memory_limit_bytes':1})['admission_status']=='not_admitted'
