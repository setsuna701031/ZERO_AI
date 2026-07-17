from core.runtime.runtime_capability_controlled_execution_outcome import build_capability_controlled_execution_outcome as build
from tests.test_runtime_capability_bounded_execution_request import request
def outcome():return build(request(),observed_status="completed",evidence_references=["evidence:inspection-1"],result_summary={"verified":True})
def test_outcome_mapping_and_safety():
    assert outcome()["status"]=="completed";assert build(request(),observed_status="failed")["status"]=="failed";assert build(request(),observed_status="completed",evidence_references=["bad\nref"])["status"]=="invalid";assert build(request(),observed_status="completed",result_summary={"x":{1}})["status"]=="invalid"
