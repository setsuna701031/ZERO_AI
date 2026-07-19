from tests.test_engineering_proposal_review_intake import review_pipeline
def test_review_invariants(tmp_path):assert all(review_pipeline(tmp_path)["review"]["review_invariants"].values())
