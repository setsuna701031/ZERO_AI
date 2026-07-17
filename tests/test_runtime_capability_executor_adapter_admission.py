from core.runtime.runtime_capability_executor_adapter_admission import build_capability_executor_adapter_admission as build
from tests.test_runtime_capability_execution_authority import authority
from tests.test_runtime_capability_bounded_execution_request import request
def adapter_admission():return build(authority(),request())
def test_admission_and_boundaries():
 assert adapter_admission()["admitted"];assert build(authority(),request(),adapter_mode="live")["admission_status"]=="blocked";assert build(authority(),request(),adapter_capabilities={"mutation":True})["admission_status"]=="blocked";assert build(authority(),request())==build(authority(),request())
