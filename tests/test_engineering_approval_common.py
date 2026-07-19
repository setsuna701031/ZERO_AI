from core.engineering.engineering_approval_common import approval_boundary,canonical_json
def test_canonical_and_authority_boundary():
 b=approval_boundary();assert canonical_json({"b":1,"a":2})=='{"a":2,"b":1}' and b["approval_authority"]=="not_granted" and b["authorization_authority"]=="not_granted"
