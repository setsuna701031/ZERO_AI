from copy import deepcopy
from core.engineering.engineering_intake_common import identified
from core.engineering.planning_request_validation import validate_engineering_planning_request
from tests.test_engineering_planning_request import planning
from tests.test_engineering_repository_analysis_request import analysis
def _fp(v):return identified({k:x for k,x in v.items() if k not in {"planning_request_id","fingerprint"}},"planning_request_id","engineering-planning-request-")
def test_planning_source_and_boundary_tamper_rejected():
 p=planning();assert validate_engineering_planning_request(p,analysis()).valid
 bad=deepcopy(p);bad["source_repository_analysis_request_id"]="other";assert not validate_engineering_planning_request(_fp(bad),analysis()).valid
 bad=deepcopy(p);bad["boundary"]["planning_started"]=True;assert not validate_engineering_planning_request(_fp(bad)).valid
