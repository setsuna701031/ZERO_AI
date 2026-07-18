from core.engineering.developer_intent import parse_developer_intent
from core.engineering.mission_bootstrap import bootstrap_engineering_mission
def intent():return parse_developer_intent("analyze repository diagnose failure and fix bug with tests")
def bootstrap():return bootstrap_engineering_mission(intent())
def test_bootstrap_is_passive_and_preserves_intent():
 b=bootstrap();i=intent();assert b["status"]=="bootstrapped" and b["bootstrap_payload"]["intent_types"]==i["intent_types"] and b["bootstrap_payload"]["required_stages"][-1]=="controlled_coding_handoff" and b["bootstrap_payload"]["mutation_allowed"] is False
def test_clarification_propagates():assert bootstrap_engineering_mission(parse_developer_intent("please help"))["status"]=="needs_clarification"
