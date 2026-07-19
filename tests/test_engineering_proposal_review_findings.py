from tests.test_engineering_proposal_review_intake import review_pipeline
def test_findings_are_stably_ordered(tmp_path):
 f=review_pipeline(tmp_path,{"validation_gaps":["x"],"scope_ambiguities":["y"]})["findings"];assert f==sorted(f,key=lambda x:(["informational","low","medium","high","critical","unknown"].index(x["severity"]),x["review_finding_id"]))
