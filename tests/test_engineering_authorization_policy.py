from tests.test_engineering_authorization_intake import authorization_pipeline
def test_policy_violation_denies_authorization():assert authorization_pipeline({"policy_violations":["no_execution_grant"]})["policy"]["status"]=="not_satisfied"
