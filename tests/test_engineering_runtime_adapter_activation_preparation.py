from tests.runtime_adapter_activation_fixtures import *
def test_preparation_mappings():
 p=pipeline(); assert p['pr']['preparation_status']=='prepared'; assert p['pr']['passive_only'] is True; assert p['pr']['adapter_loaded'] is False
 assert build_runtime_adapter_activation_preparation(dict(p['ad'],admission_status='not_admitted'),p['pp'])['preparation_status']=='not_prepared'
 assert build_runtime_adapter_activation_preparation(p['ad'],p['pp'],{'command':'x'})['preparation_status']=='not_prepared'
 assert build_runtime_adapter_activation_preparation(p['ad'],p['pp'],{'passive_only':True},{'max_units':0})['preparation_status']=='not_prepared'
 assert build_runtime_adapter_activation_preparation(p['ad'],p['pp'],{'passive_only':True},{'max_units':1},{'seconds':0})['preparation_status']=='not_prepared'
