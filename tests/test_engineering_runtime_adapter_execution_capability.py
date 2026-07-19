from tests.runtime_adapter_execution_integration_fixtures import *
def test_capability_valid_and_rejects_payload():
 p=pipeline(); assert p['cap']['capability_status']=='declared' and validate_runtime_adapter_execution_capability(p['cap']).valid
 bad=build_runtime_adapter_execution_capability(adapter_id='a',adapter_version='1',supported_operation_names=['x'],command='run')
 assert bad['capability_status']=='invalid'
