from core.engineering.engineering_execution_admission import build_engineering_execution_admission
def test_admission_does_not_grant_authority():
 value=build_engineering_execution_admission({"status":"accepted","sealed_execution_scope":{}})
 assert value["admission_decision"]=="admitted" and value["authority_declarations"]["execution_authority"]=="not_granted"
