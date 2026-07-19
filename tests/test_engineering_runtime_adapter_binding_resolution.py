from tests.runtime_adapter_execution_integration_fixtures import *
def test_binding_and_mismatch():
 p=pipeline(); assert p['br']['binding_status']=='resolved'
 cap=dict(p['cap']); cap['adapter_id']='other'; assert build_runtime_adapter_binding_resolution(p['req'],cap)['binding_status']=='invalid'
