from copy import deepcopy
from core.engineering.engineering_planning_verification import verify_engineering_plan
from tests.test_engineering_planning_closure import pipeline
def test_verification_fails_missing_coverage(tmp_path):
 p=pipeline(tmp_path)[0];assert verify_engineering_plan(p)["status"]=="verified"
 p=deepcopy(p);p["validation_strategy"]=[];assert verify_engineering_plan(p)["status"]=="invalid"
