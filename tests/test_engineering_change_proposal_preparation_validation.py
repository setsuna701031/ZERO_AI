from copy import deepcopy
from core.engineering.engineering_intake_common import identified
from core.engineering.change_proposal_preparation_validation import validate_change_proposal_preparation
from tests.test_engineering_change_proposal_preparation import preparation
from tests.test_engineering_planning_request import planning
def _fp(v):return identified({k:x for k,x in v.items() if k not in {"change_proposal_preparation_id","fingerprint"}},"change_proposal_preparation_id","engineering-change-proposal-preparation-")
def test_preparation_linkage_and_authority_rejection():
 p=preparation();assert validate_change_proposal_preparation(p,planning()).valid
 bad=deepcopy(p);bad["preparation_payload"]["approval_token"]="fake";assert not validate_change_proposal_preparation(_fp(bad)).valid
