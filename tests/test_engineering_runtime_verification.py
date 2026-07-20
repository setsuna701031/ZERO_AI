from core.engineering.engineering_runtime_orchestrator import orchestrate_engineering_runtime
from tests.engineering_runtime_orchestrator_fixtures import request_payload
def test_end_to_end_verification(): assert orchestrate_engineering_runtime(request_payload())["verification"]["status"]=="verified"
