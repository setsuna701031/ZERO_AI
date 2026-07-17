from core.runtime.runtime_capability_bounded_execution_request import build_capability_bounded_execution_request as build
from tests.test_runtime_capability_execution_authority import authority
def request():return build(authority(),operation_class="inspect",target_descriptor={"resource":"profile"},bounded_parameters={"depth":1})
def test_request_allowlist_scope_and_count():
    assert request()["status"]=="accepted";assert build(authority(),operation_class="write",target_descriptor={"resource":"profile"})["status"]=="blocked";assert build(authority(),operation_class="inspect",target_descriptor={"other":1})["status"]=="blocked";assert build(authority(),operation_class="inspect",target_descriptor={"resource":"profile"},request_ordinal=2)["status"]=="blocked"
