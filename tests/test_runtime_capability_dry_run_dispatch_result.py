from core.runtime.runtime_capability_dry_run_dispatch_result import build_capability_dry_run_dispatch_result as build
from tests.test_runtime_capability_dry_run_dispatch_plan import plan
def result():return build(plan(),observed_status="simulated",observation_summary={"dry_run_simulation_generated":True},evidence_references=["evidence:missing-is-not-read"])
def test_result_invariants():
 assert result()["result_status"]=="simulated" and result()["side_effects_performed"]==[];assert build(plan(),observed_status="completed")["result_status"]=="invalid";assert build(plan(),observed_status="simulated",side_effects_performed=["read"])["result_status"]=="invalid"
