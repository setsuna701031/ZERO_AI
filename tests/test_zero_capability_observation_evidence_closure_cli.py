from cli import zero_capability_observation_evidence_closure as cli
from core.runtime.runtime_capability_observation_evidence_closure_validation import validate_capability_observation_evidence_closure as validate
from tests.test_runtime_capability_execution_authority import authority
from tests.test_runtime_capability_bounded_execution_request import request
from tests.test_runtime_capability_executor_bridge_verification_closure import bridge_closure
from tests.test_runtime_capability_read_only_adapter_admission import admission
from tests.test_runtime_capability_bounded_observation_request import observation_request
from tests.test_runtime_capability_safe_target_resolution import resolution
from tests.test_runtime_capability_read_only_observation_result import result
def test_cli(monkeypatch,tmp_path):
 (tmp_path/"target.txt").touch();vals=dict(zip(("a","r","c","d","q","z","x"),(authority(),request(),bridge_closure(),admission(tmp_path),observation_request(root=tmp_path),resolution(tmp_path),result(tmp_path))));monkeypatch.setattr(cli,"_read",vals.get);args=[]
 for n,v in zip(("authority","execution-request","bridge-closure","admission","observation-request","target-resolution","observation-result"),vals):args += ["--"+n,v]
 x,c=cli.run(args);assert c==0 and validate(x).valid
