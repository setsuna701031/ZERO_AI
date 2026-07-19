from tests.test_engineering_proposal_closure import proposal_pipeline
def test_ready_is_not_approved(tmp_path):
 p=proposal_pipeline(tmp_path)[0];assert p["status"]=="ready_for_review" and p["proposal_intake"]["governance_declarations"]["approved"] is False and all(p["proposal_invariants"].values())
