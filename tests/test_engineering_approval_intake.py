from core.engineering.engineering_intake_common import identified
from cli.zero_engineering_approval import build_pipeline
def review_closure():
 p={"schema":"zero.engineering.proposal_review_closure.v1","status":"closed","engineering_proposal_review_id":"review-1","proposal_closure_id":"proposal-closure-1","engineering_proposal_id":"proposal-1","planning_closure_id":"planning-1","repository_identity":"repo","analyzed_revision":"abc","governance_boundary_declaration":{"authorization_granted":False,"execution_granted":False,"mutation_granted":False},"next_boundary_declaration":{"foundation":"Engineering Approval Foundation"},"boundary":{"sealed":True}};return identified(p,"proposal_review_closure_id","engineering-proposal-review-closure-")
def approval_pipeline(intent=None):return build_pipeline(review_closure(),intent or {})
def test_review_closure_intake_is_accepted():assert approval_pipeline()["intake"]["status"]=="accepted"
