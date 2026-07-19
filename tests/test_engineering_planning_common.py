from core.engineering.engineering_planning_common import canonical_json,fingerprint,stable_id
def test_canonical_and_stable():
 assert canonical_json({"b":1,"a":2})=='{"a":2,"b":1}'
 assert fingerprint({"a":1})==fingerprint({"a":1}) and stable_id("x-",{"a":1}).startswith("x-")
