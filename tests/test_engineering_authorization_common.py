from core.engineering.engineering_authorization_common import authorization_boundary,canonical_json
def test_canonical_authority_boundary():
 b=authorization_boundary();assert canonical_json({"b":1,"a":2})=='{"a":2,"b":1}' and b["approval_authority"]=="granted" and b["authorization_authority"]=="not_granted" and b["execution_authority"]=="not_granted"
