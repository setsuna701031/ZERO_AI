from tests.runtime_adapter_activation_fixtures import *
def test_closure():
 p=pipeline(); c=p['cl']; assert c['package_status']=='closed'; assert c['no_real_adapter_loading_invariant']; assert c['adapter_invocation_prohibition']; assert c['runtime_kernel_invocation_prohibition']; assert c['external_authority_consumption_prohibition']; assert c['mutation_prohibition']
 bad=build_runtime_adapter_activation_boundary_closure(p['ar'],p['ap'],dict(p['ad'],admission_status='not_admitted'),p['pp'],p['pr'],p['ca'],p['tc'],p['rs'],p['vf'],p['ho']); assert bad['package_status']=='not_closed'
