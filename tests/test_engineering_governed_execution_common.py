from core.engineering.engineering_governed_execution_common import contains_forbidden, fingerprint
def test_common_is_deterministic_and_rejects_payloads():
 assert fingerprint({"b":2,"a":1})==fingerprint({"a":1,"b":2})
 assert contains_forbidden({"patch":"x"})
