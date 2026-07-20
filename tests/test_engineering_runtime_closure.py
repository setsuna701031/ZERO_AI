from core.engineering.engineering_runtime_orchestrator import orchestrate_engineering_runtime
from tests.engineering_runtime_orchestrator_fixtures import request_payload
def test_preview_closes(): assert orchestrate_engineering_runtime(request_payload())["closure"]["status"]=="closed"
