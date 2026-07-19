from copy import deepcopy
import pytest
from core.engineering.engineering_proposal_intake import build_engineering_proposal_intake,validate_engineering_proposal_intake
from tests.test_engineering_planning_closure import pipeline
def proposal_planning_closure(tmp_path):return pipeline(tmp_path)[2]
def test_closed_intake_and_fail_closed(tmp_path):
 c=proposal_planning_closure(tmp_path);a=build_engineering_proposal_intake(c);assert a==build_engineering_proposal_intake(c) and validate_engineering_proposal_intake(a).valid
 for status in ("blocked","invalid"):
  bad=deepcopy(c);bad["status"]=status
  with pytest.raises(ValueError):build_engineering_proposal_intake(bad)
 bad=deepcopy(c);bad["fingerprint"]="0"*64
 with pytest.raises(ValueError):build_engineering_proposal_intake(bad)
 with pytest.raises(ValueError):build_engineering_proposal_intake(c,{"requested_scope":["src"]})
