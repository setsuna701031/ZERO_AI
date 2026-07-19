from tests.test_engineering_approval_intake import approval_pipeline
def test_unresolved_condition_is_preserved():assert approval_pipeline({"conditions":["human review"],"satisfied_conditions":[]})["conditions"]["status"]=="unresolved"
