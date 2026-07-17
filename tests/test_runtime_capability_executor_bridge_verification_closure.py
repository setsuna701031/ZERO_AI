from core.runtime.runtime_capability_executor_bridge_verification_closure import close_capability_executor_bridge_verification as build
from tests.test_runtime_capability_execution_authority import authority
from tests.test_runtime_capability_bounded_execution_request import request
from tests.test_runtime_capability_executor_adapter_admission import adapter_admission
from tests.test_runtime_capability_dry_run_dispatch_plan import plan
from tests.test_runtime_capability_dry_run_dispatch_result import result
from tests.test_runtime_capability_runtime_outcome_reconciliation import reconciliation
def bridge_closure(**kw):return build(authority(),request(),adapter_admission(),plan(),result(),reconciliation(),**kw)
def test_bridge_only_and_completed_rejected():assert bridge_closure()["verification_status"]=="verified_closed";assert bridge_closure(controlled_execution_outcome={"status":"completed","outcome_id":"o","fingerprint":"f"})["verification_status"]=="blocked"
