from pathlib import Path
from core.engineering.repository_analysis import analyze_repository
from core.engineering.engineering_planning_context import build_engineering_planning_context,validate_engineering_planning_context
from tests.test_engineering_repository_analysis_foundation import fixture
from tests.test_engineering_repository_analysis_request import analysis
def planning_fixture(tmp_path:Path):return analyze_repository(analysis(),fixture(tmp_path))
def test_context_is_stable_and_bounded(tmp_path):
 c=planning_fixture(tmp_path);a=build_engineering_planning_context(c);b=build_engineering_planning_context(c)
 assert a==b and validate_engineering_planning_context(a).valid
