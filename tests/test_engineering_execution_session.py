from core.engineering.engineering_execution_session import build_engineering_execution_session
def test_session_authority_is_bounded():
 value=build_engineering_execution_session({"admission_decision":"admitted","admitted_scope":{}},{})
 assert value["session_authority"]["non_reusable"] and value["session_authority"]["mutation_authority"]=="not_granted"
