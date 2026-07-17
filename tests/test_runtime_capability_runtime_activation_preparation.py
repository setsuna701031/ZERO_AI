from core.runtime.runtime_capability_runtime_activation_preparation import prepare_capability_runtime_activation as build
from tests.test_runtime_capability_runtime_activation_eligibility import eligibility
def preparation(value=None,at="2099-07-17T06:03:22Z"):return build(eligibility() if value is None else value,prepared_at=at)
def test_prepared_safe():
 x=preparation();assert x["prepared"] and x["runtime_activation_preparation_created"] and not x["runtime_admission_created"] and preparation(at="2099-07-17T06:03:20Z")["blocked"]
