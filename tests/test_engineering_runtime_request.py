from core.engineering.engineering_runtime_request import *
from tests.engineering_runtime_orchestrator_fixtures import request_payload
def test_request_deterministic_and_bounded():
 assert build_engineering_runtime_request(request_payload())==build_engineering_runtime_request(request_payload()); assert build_engineering_runtime_request({**request_payload(),"command":"x"})["status"]=="invalid"
