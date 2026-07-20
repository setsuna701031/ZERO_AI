from core.engineering.engineering_runtime_request import build_engineering_runtime_request
from core.engineering.engineering_runtime_session import *
from tests.engineering_runtime_orchestrator_fixtures import request_payload
def test_session_identity_and_terminal_immutability():
 r=build_engineering_runtime_request(request_payload()); a=build_engineering_runtime_session(r); assert a["session_id"]==build_engineering_runtime_session(r)["session_id"]; assert transition_session(transition_session(a,"succeeded"),"executing")["status"]=="invalid"
