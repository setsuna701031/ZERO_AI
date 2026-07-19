import pytest
from core.engineering.engineering_planning_context import build_engineering_planning_context
from core.engineering.engineering_goal_extraction import extract_engineering_goals
from tests.test_engineering_planning_context import planning_fixture
def test_goals_trace_evidence(tmp_path):
 c=build_engineering_planning_context(planning_fixture(tmp_path));g=extract_engineering_goals(c);assert g[0]["source_evidence_references"]
 with pytest.raises(ValueError):extract_engineering_goals(c,{"goals":[{"title":"x","description":"x","evidence_references":["fake"]}]})
