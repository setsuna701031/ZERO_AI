from core.engineering.engineering_governed_execution_closure import build_engineering_governed_execution_closure
def test_closure_consumes_authority():
 value=build_engineering_governed_execution_closure({}, {}, {}, {}, {"result_status":"completed"},{"verification_status":"verified"})
 assert value["closure_status"]=="closed_completed" and value["authority_closure_declaration"]["reusable_execution_token"] is False
