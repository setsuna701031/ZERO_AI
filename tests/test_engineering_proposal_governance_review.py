from tests.test_engineering_proposal_review_intake import review_pipeline
def test_authority_is_rejected(tmp_path):assert review_pipeline(tmp_path,{"approved":True})["governance"]["status"]=="invalid"
