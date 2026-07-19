from tests.test_engineering_authorization_intake import authorization_pipeline
def test_only_closure_grants_authorization():
 x=authorization_pipeline();assert x["decision"]["boundary"]["authorization_authority"]=="not_granted" and x["closure"]["status"]=="closed_authorized" and x["closure"]["boundary"]["authorization_authority"]=="granted" and x["closure"]["boundary"]["execution_authority"]=="not_granted" and x["closure"]["next_boundary_declaration"]["destination"]=="Execution Preparation"
