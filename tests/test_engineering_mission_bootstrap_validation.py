from copy import deepcopy
from core.engineering.engineering_intake_common import identified
from core.engineering.mission_bootstrap_validation import validate_engineering_mission_bootstrap
from tests.test_engineering_mission_bootstrap import bootstrap,intent
def _fp(v):return identified({k:x for k,x in v.items() if k not in {"mission_bootstrap_id","fingerprint"}},"mission_bootstrap_id","engineering-mission-bootstrap-")
def test_source_monotonic_and_refingerprinted_tamper():
 b=bootstrap();assert validate_engineering_mission_bootstrap(b,intent()).valid
 bad=deepcopy(b);bad["bootstrap_payload"]["intent_types"].append("add_feature");assert not validate_engineering_mission_bootstrap(_fp(bad),intent()).valid
def test_status_and_authority_promotion_rejected():
 bad=deepcopy(bootstrap());bad["boundary"]["authority_granted"]=True;assert not validate_engineering_mission_bootstrap(_fp(bad)).valid
