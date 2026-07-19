from tests.test_engineering_approval_intake import approval_pipeline
def test_policy_violation_rejects_eligibility():assert approval_pipeline({"policy_violations":["no_repository_mutation"]})["policy"]["status"]=="not_satisfied"
