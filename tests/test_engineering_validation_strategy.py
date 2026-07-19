from core.engineering.engineering_validation_strategy import build_engineering_validation_strategy
def test_validation_is_descriptive():
 v=build_engineering_validation_strategy([{"goal_id":"g"}],[{"goal_id":"g","work_item_id":"w"}]);assert len(v)==3 and all(not x["long_running"] for x in v)
