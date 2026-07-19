from tests.test_engineering_approval_intake import approval_pipeline
def test_decision_does_not_grant_authority():
 d=approval_pipeline()["decision"];assert d["decision"]=="approved" and d["boundary"]["approval_authority"]=="not_granted" and d["boundary"]["execution_authority"]=="not_granted"
