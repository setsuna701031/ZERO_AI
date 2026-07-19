from tests.test_engineering_authorization_intake import authorization_pipeline
def test_unresolved_constraint_is_preserved():assert authorization_pipeline({"authorization_constraints":["human control"],"satisfied_constraints":[]})["constraints"]["status"]=="unresolved"
