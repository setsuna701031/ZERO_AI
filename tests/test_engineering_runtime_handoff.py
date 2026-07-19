from core.engineering.engineering_runtime_handoff import build_engineering_runtime_handoff
def test_handoff_is_passive():
 value=build_engineering_runtime_handoff({"status":"prepared","sealed_scope":{}})
 assert value["status"]=="prepared" and not value["boundary"]["runtime_invoked"]
