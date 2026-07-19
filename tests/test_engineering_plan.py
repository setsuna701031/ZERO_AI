from tests.test_engineering_planning_closure import pipeline
def test_plan_invariants(tmp_path):
 p=pipeline(tmp_path)[0];assert p["status"]=="valid" and all(p["planning_invariants"].values())
