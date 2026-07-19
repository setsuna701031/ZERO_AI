from tests.test_engineering_proposal_review_intake import review_pipeline
def test_closure_next_boundary_and_authority(tmp_path):
 c=review_pipeline(tmp_path)["closure"];assert c["status"]=="closed" and c["next_boundary_declaration"]["foundation"]=="Engineering Approval Foundation" and not c["governance_boundary_declaration"]["approval_granted"]
