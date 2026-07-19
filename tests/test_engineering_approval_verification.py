from tests.test_engineering_approval_intake import approval_pipeline
def test_approval_verifies_without_execution_authority():assert approval_pipeline()["verification"]["status"]=="verified"
