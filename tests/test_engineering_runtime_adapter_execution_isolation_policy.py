from tests.runtime_adapter_execution_integration_fixtures import *
def test_isolation_levels():
 assert build_runtime_adapter_execution_isolation_policy(isolation_level='sandbox_required')['isolation_status']=='valid'
 assert build_runtime_adapter_execution_isolation_policy(isolation_level='real')['isolation_status']=='invalid'
