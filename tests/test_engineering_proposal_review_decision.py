from tests.test_engineering_proposal_review_intake import review_pipeline
def test_ready_does_not_mean_approved(tmp_path):
 d=review_pipeline(tmp_path)["decision"];assert d["decision"]=="ready_for_approval" and d["authority_declarations"]["approval_authority"]=="not_granted"
