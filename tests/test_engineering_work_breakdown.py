from core.engineering.engineering_planning_context import build_engineering_planning_context
from core.engineering.engineering_goal_extraction import extract_engineering_goals
from core.engineering.engineering_work_breakdown import build_engineering_work_breakdown
from tests.test_engineering_planning_context import planning_fixture
def test_work_has_no_authority(tmp_path):
 c=build_engineering_planning_context(planning_fixture(tmp_path));w=build_engineering_work_breakdown(extract_engineering_goals(c))[0]
 assert "approval granting" in w["forbidden_actions"] and "implement" in w["allowed_actions"]
