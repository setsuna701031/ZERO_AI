from tests.test_engineering_authorization_intake import authorization_pipeline
def test_evidence_gap_fails_closed():assert authorization_pipeline({"evidence_gaps":["missing"]})["eligibility"]["status"]=="insufficient_evidence"
