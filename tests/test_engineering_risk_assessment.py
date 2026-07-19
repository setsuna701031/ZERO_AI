from core.engineering.engineering_risk_assessment import build_engineering_risk_assessment
def test_unknown_is_preserved():
 c={"evidence_references":["e"]};r=build_engineering_risk_assessment(c,[],[]);assert r[0]["likelihood"]=="unknown"
