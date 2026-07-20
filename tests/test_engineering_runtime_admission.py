from core.engineering.engineering_runtime_request import build_engineering_runtime_request
from core.engineering.engineering_runtime_session import build_engineering_runtime_session
from core.engineering.engineering_runtime_admission import *
from tests.engineering_runtime_orchestrator_fixtures import request_payload
def test_admission_workspace_binding():
 r=build_engineering_runtime_request(request_payload()); s=build_engineering_runtime_session(r); assert admit_engineering_runtime(r,s,{"workspace_id":"workspace-1","workspace_root_fingerprint":"root-fingerprint"})["status"]=="admitted"; assert admit_engineering_runtime(r,s,{})["status"]=="not_admitted"
