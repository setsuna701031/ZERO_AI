from cli import zero_capability_read_only_observation_result as cli
from core.runtime.runtime_capability_read_only_observation_result_validation import validate_capability_read_only_observation_result as validate
from tests.test_runtime_capability_read_only_adapter_admission import admission
from tests.test_runtime_capability_bounded_observation_request import observation_request
from tests.test_runtime_capability_safe_target_resolution import resolution
def test_cli(monkeypatch,tmp_path):
 (tmp_path/"target.txt").touch();vals={"a":admission(tmp_path),"q":observation_request(root=tmp_path),"z":resolution(tmp_path)};monkeypatch.setattr(cli,"_read",vals.get);x,c=cli.run(["--admission","a","--observation-request","q","--target-resolution","z"]);assert c==0 and validate(x).valid
