from core.runtime.runtime_capability_execution_authority import issue_capability_execution_authority as build
from tests.test_runtime_capability_execution_session_admission import admission
def authority():return build(admission(),issued_scope={"resource":"profile"})
def test_authority_defaults_and_forbidden():
    x=authority();assert x["status"]=="authorized" and all(x["authority_constraints"][n] is False for n in ("mutation_permission","external_process_permission","network_permission","model_invocation_permission"))
    assert build(admission(),authority_constraints={"network_permission":True})["status"]=="blocked"
