from tests.test_engineering_approval_intake import approval_pipeline
def test_only_closure_grants_approval():
 x=approval_pipeline();assert x["decision"]["boundary"]["approval_authority"]=="not_granted" and x["closure"]["status"]=="closed_approved" and x["closure"]["boundary"]["approval_authority"]=="granted" and x["closure"]["authorization_authority_declaration"]=="not_granted"
