from core.runtime.runtime_capability_read_only_adapter_admission import build_capability_read_only_adapter_admission as build
from tests.test_runtime_capability_execution_authority import authority
from tests.test_runtime_capability_bounded_execution_request import request
from tests.test_runtime_capability_executor_bridge_verification_closure import bridge_closure
def admission(root="."):return build(authority(),request(),bridge_closure(),workspace_root_descriptor={"path":str(root)})
def test_admission_boundaries():
 assert admission()["admitted"] and admission()==admission()
 assert build(authority(),request(),bridge_closure(),workspace_root_descriptor={"path":"."},adapter_mode="live")["admission_status"]=="blocked"
 assert build(authority(),request(),bridge_closure(),workspace_root_descriptor={"path":"."},adapter_capabilities={"filesystem_read":True})["admission_status"]=="blocked"
