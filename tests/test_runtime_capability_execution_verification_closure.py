from core.runtime.runtime_capability_execution_verification_closure import close_capability_execution_verification as build
from tests.test_runtime_capability_execution_session_admission import admission
from tests.test_runtime_capability_execution_authority import authority
from tests.test_runtime_capability_bounded_execution_request import request
from tests.test_runtime_capability_controlled_execution_outcome import outcome
def closure():return build(admission(),authority(),request(),outcome())
def test_closure_and_linkage_fail_safe():
    x=closure();assert x["status"]=="verified_closed" and x["closed"] is True
    o=outcome();o["request_id"]="wrong";assert build(admission(),authority(),request(),o)["status"]=="invalid"
