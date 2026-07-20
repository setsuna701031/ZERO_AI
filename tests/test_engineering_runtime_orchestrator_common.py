from core.engineering.engineering_runtime_orchestrator_common import canonical_json,fingerprint,prohibited
def test_common_is_deterministic_and_rejects_authority_payloads():
 assert fingerprint({"b":2,"a":1})==fingerprint({"a":1,"b":2}); assert canonical_json({"b":2,"a":1})=='{"a":1,"b":2}'; assert prohibited({"password":"x"})
