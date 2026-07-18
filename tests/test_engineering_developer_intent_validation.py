from copy import deepcopy
from core.engineering.developer_intent import parse_developer_intent
from core.engineering.developer_intent_validation import validate_developer_intent
from core.engineering.engineering_intake_common import identified
def _fp(v):return identified({k:x for k,x in v.items() if k not in {"developer_intent_id","fingerprint"}},"developer_intent_id","engineering-developer-intent-")
def test_identity_boundary_unknown_and_forbidden_rejection():
 v=parse_developer_intent("inspect repository");assert validate_developer_intent(v).valid
 for bad in ({**v,"extra":1},{k:x for k,x in v.items() if k!="status"}):assert not validate_developer_intent(bad).valid
 bad=deepcopy(v);bad["boundary"]["mutation_allowed"]=True;assert not validate_developer_intent(_fp(bad)).valid
 bad=deepcopy(v);bad["risk_flags"].append("rm -rf");assert not validate_developer_intent(_fp(bad)).valid
