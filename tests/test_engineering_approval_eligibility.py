from tests.test_engineering_approval_intake import approval_pipeline
def test_evidence_gap_fails_closed():assert approval_pipeline({"evidence_gaps":["missing"]})["eligibility"]["status"]=="insufficient_evidence"
