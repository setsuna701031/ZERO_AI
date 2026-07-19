from core.engineering.engineering_proposal_risk_review import build_engineering_proposal_risk_review
def test_unknown_and_gate_declarations():
 c=[{"proposed_change_id":"c"}];r=build_engineering_proposal_risk_review(c,["e"],{"risks":[{"category":"approval bypass risk","description":"gate","evidence_references":["e"],"affected_proposed_change_ids":["c"],"approval_blocking":True,"authorization_blocking":True}]})[0]
 assert r["likelihood"]=="unknown" and r["approval_blocking"] and r["authorization_blocking"] and not r["proposal_blocking"]
