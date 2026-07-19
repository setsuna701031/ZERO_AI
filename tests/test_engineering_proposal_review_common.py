from core.engineering.engineering_proposal_review_common import canonical_json,review_boundary
def test_canonical_and_read_only_boundary():
 assert canonical_json({"b":1,"a":2})=='{"a":2,"b":1}' and not review_boundary()["repository_modified"]
