from tests.test_engineering_proposal_review_intake import review_pipeline
def test_validation_gap_requests_changes(tmp_path):assert review_pipeline(tmp_path,{"validation_gaps":["regression"]})["validation"]["status"]=="changes_required"
