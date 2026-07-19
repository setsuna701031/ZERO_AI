from tests.test_engineering_authorization_intake import authorization_pipeline
def test_decision_is_not_execution():
 d=authorization_pipeline()["decision"];assert d["decision"]=="authorized" and d["boundary"]["authorization_authority"]=="not_granted" and d["boundary"]["execution_authority"]=="not_granted"
