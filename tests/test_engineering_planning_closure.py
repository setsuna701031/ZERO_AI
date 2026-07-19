from core.engineering.engineering_planning_context import build_engineering_planning_context
from core.engineering.engineering_goal_extraction import extract_engineering_goals
from core.engineering.engineering_work_breakdown import build_engineering_work_breakdown
from core.engineering.engineering_dependency_ordering import build_engineering_dependency_ordering
from core.engineering.engineering_validation_strategy import build_engineering_validation_strategy
from core.engineering.engineering_risk_assessment import build_engineering_risk_assessment
from core.engineering.engineering_plan import build_engineering_plan
from core.engineering.engineering_planning_verification import verify_engineering_plan
from core.engineering.engineering_planning_closure import build_engineering_planning_closure
from tests.test_engineering_planning_context import planning_fixture
def pipeline(tmp_path):
 c=build_engineering_planning_context(planning_fixture(tmp_path));g=extract_engineering_goals(c);w=build_engineering_work_breakdown(g);d=build_engineering_dependency_ordering(w);v=build_engineering_validation_strategy(g,w);r=build_engineering_risk_assessment(c,g,w);p=build_engineering_plan(c,g,w,d,v,r);q=verify_engineering_plan(p);return p,q,build_engineering_planning_closure(p,q)
def test_only_verified_closes(tmp_path):
 p,v,c=pipeline(tmp_path);assert v["status"]=="verified" and c["status"]=="closed" and not c["next_boundary_declaration"]["mutation_authorized"]
