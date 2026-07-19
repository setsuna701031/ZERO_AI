from core.engineering.engineering_execution_observation import build_engineering_execution_observation
def test_missing_result_is_insufficient():
 assert build_engineering_execution_observation({}, {}, None)["status"]=="insufficient_evidence"
