from tests.test_engineering_authorization_intake import authorization_pipeline
def test_verification_preserves_no_execution():assert authorization_pipeline()["verification"]["status"]=="verified"
