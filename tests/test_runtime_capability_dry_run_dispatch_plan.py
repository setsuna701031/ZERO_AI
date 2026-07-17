from core.runtime.runtime_capability_dry_run_dispatch_plan import build_capability_dry_run_dispatch_plan as build
from tests.test_runtime_capability_executor_adapter_admission import adapter_admission
from tests.test_runtime_capability_bounded_execution_request import request
def plan():return build(adapter_admission(),request())
def test_plan_invariants():
 assert plan()["plan_status"]=="planned" and plan()["expected_effects"]==[];assert build(adapter_admission(),request(),dispatch_ordinal=True)["plan_status"]=="invalid";assert build(adapter_admission(),request(),target_descriptor={"expanded":True})["plan_status"]=="blocked"
