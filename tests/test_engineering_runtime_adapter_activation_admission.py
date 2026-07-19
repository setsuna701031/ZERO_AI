from tests.runtime_adapter_activation_fixtures import *
from core.engineering.engineering_runtime_adapter_activation_common import canonical_json
def test_admission_mappings_and_rejections():
 p=pipeline(); assert p['ad']['admission_status']=='admitted'; assert validate_runtime_adapter_activation_admission(p['ad']).valid; assert canonical_json(p['ad'])==canonical_json(p['ad'])
 assert pipeline(token_issued=False)['ad']['admission_status']=='not_admitted'; assert pipeline(token_verified=False)['ad']['admission_status']=='not_admitted'; assert pipeline(token_consumed=True)['ad']['admission_status']=='not_admitted'; assert pipeline(adapter_id='other')['ad']['admission_status']=='admitted'
 h=token_handoff(max_uses=2); r=build_runtime_adapter_activation_admission_request(h); assert build_runtime_adapter_activation_admission(r,build_default_runtime_adapter_activation_admission_policy(),h)['admission_status']=='not_admitted'
 h=token_handoff(activation_scope='*'); r=build_runtime_adapter_activation_admission_request(h); assert build_runtime_adapter_activation_admission(r,build_default_runtime_adapter_activation_admission_policy(),h)['admission_status']=='not_admitted'
