from core.engineering.engineering_governed_execution_intake import build_engineering_governed_execution_intake
def test_intake_fail_closed_and_deterministic():
 closure={"schema":"zero.engineering.execution_preparation_closure.v1","status":"closed_ready","preparation_decision":"ready_for_governed_execution","approval_authority_declaration":"granted","authorization_authority_declaration":"granted","execution_authority_declaration":"not_granted","mutation_authority_declaration":"not_granted"}
 assert build_engineering_governed_execution_intake(closure)==build_engineering_governed_execution_intake(closure)
 assert build_engineering_governed_execution_intake({},{} )["status"]=="invalid"
