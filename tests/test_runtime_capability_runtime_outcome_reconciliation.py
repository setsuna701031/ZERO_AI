from core.runtime.runtime_capability_runtime_outcome_reconciliation import build_capability_runtime_outcome_reconciliation as build
from tests.test_runtime_capability_execution_authority import authority
from tests.test_runtime_capability_bounded_execution_request import request
from tests.test_runtime_capability_executor_adapter_admission import adapter_admission
from tests.test_runtime_capability_dry_run_dispatch_plan import plan
from tests.test_runtime_capability_dry_run_dispatch_result import result
def reconciliation():return build(authority(),request(),adapter_admission(),plan(),result())
def test_reconciliation_never_completes():x=reconciliation();assert x["reconciliation_status"]=="reconciled" and x["execution_completion_claim"] is False and x["recommended_v1_2_outcome_status"]=="not_completed"
