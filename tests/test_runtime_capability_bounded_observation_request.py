from core.runtime.runtime_capability_bounded_observation_request import build_capability_bounded_observation_request as build,HARD_LIMITS
from tests.test_runtime_capability_read_only_adapter_admission import admission
from tests.test_runtime_capability_bounded_execution_request import request
def limits():return dict(HARD_LIMITS)
def observation_request(kind="existence",target="target.txt",root="."):return build(admission(root),request(),observation_kind=kind,relative_target=target,limits=limits())
def test_request_paths_limits_and_kinds():
 assert observation_request()["accepted"] and observation_request()==observation_request()
 for target in ("","../x","C:foo","/x","\\\\server\\x","a:b","a//b","a\x00b"):assert observation_request(target=target)["request_status"]=="blocked"
 assert build(admission(),request(),observation_kind="recursive",relative_target="x",limits=limits())["request_status"]=="blocked"
 assert build(admission(),request(),observation_kind="existence",relative_target="x",limits={**limits(),"max_file_bytes":4194305})["request_status"]=="blocked"
