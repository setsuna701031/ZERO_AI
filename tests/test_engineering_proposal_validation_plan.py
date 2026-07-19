from core.engineering.engineering_proposal_validation_plan import build_engineering_proposal_validation_plan
def test_validation_coverage_and_long_running():
 c=[{"proposed_change_id":"c","work_item_id":"w"}];v=build_engineering_proposal_validation_plan(c,{"validations":[{"target_proposed_change_ids":["c"],"source_planning_validation_ids":["v"],"category":"integration validation","validation_objective":"bounded","long_running":True}]})
 assert v[0]["long_running"] and v[0]["required_before_approval"] and v[0]["required_before_authorization"]
