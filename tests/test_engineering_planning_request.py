from core.engineering.planning_request import build_engineering_planning_request
from tests.test_engineering_repository_analysis_request import analysis
def planning():return build_engineering_planning_request(analysis())
def test_planning_request_has_required_outputs_without_plan():
 p=planning();assert p["status"]=="planned_request" and "bounded_change_plan" in p["planning_request_payload"]["expected_outputs"] and "execution_plan" not in p["planning_request_payload"]
