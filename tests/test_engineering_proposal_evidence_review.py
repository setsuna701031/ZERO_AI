from tests.test_engineering_proposal_review_intake import review_pipeline
def test_missing_evidence_fails_closed(tmp_path):assert review_pipeline(tmp_path,{"required_evidence":["missing"]})["evidence"]["status"]=="insufficient"
