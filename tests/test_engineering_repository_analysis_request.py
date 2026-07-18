from core.engineering.repository_analysis_request import prepare_repository_analysis_request
from tests.test_engineering_mission_bootstrap import bootstrap
def analysis():return prepare_repository_analysis_request(bootstrap())
def test_analysis_request_does_not_analyze_or_guess_path():
 a=analysis();p=a["analysis_request_payload"];assert a["status"]=="prepared" and p["repository_scope"]=="current_repository" and "analysis_results" not in p and "shell_command" not in p
