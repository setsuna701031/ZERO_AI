from tests.test_engineering_proposal_review_intake import review_pipeline
def test_unknown_risk_is_preserved(tmp_path):assert review_pipeline(tmp_path,{"unknown_risks":["unknown"]})["risks"]["unknown_risk_findings"]==["unknown"]
