from tests.test_engineering_proposal_review_intake import review_pipeline
def test_review_verifies(tmp_path):assert review_pipeline(tmp_path)["verification"]["status"]=="verified"
