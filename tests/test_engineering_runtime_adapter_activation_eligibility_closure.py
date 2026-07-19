from tests.runtime_adapter_activation_eligibility_fixtures import chain,request
from core.engineering.engineering_runtime_adapter_activation_eligibility_closure import *
def test_closed_mapping_no_activation_implications():
 *_,clo=chain(); assert clo['package_status']=='closed'; assert validate_runtime_adapter_activation_eligibility_closure(clo).valid
 for k in ('activation_authorization_prohibited','activation_token_prohibited','adapter_loading_prohibited','adapter_activation_prohibited','adapter_invocation_prohibited','runtime_invocation_prohibited','authority_consumption_prohibited','mutation_prohibited'): assert clo[k] is True
def test_invalid_and_not_closed_mapping():
 *_,clo=chain(request(preparation_review_status='rejected')); assert clo['package_status']=='invalid'
