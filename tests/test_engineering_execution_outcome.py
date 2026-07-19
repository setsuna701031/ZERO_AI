from core.engineering.engineering_execution_outcome import build_engineering_execution_outcome
def test_no_false_completion():
 value=build_engineering_execution_outcome({}, {}, {"lifecycle_state":"completed"},{"integrity_status":"insufficient"})
 assert value["result_status"]=="insufficient_evidence"
