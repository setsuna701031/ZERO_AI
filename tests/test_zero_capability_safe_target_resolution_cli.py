from cli import zero_capability_safe_target_resolution as cli
from core.runtime.runtime_capability_safe_target_resolution_validation import validate_capability_safe_target_resolution as validate
from tests.test_runtime_capability_read_only_adapter_admission import admission
from tests.test_runtime_capability_bounded_observation_request import observation_request
def test_cli(monkeypatch,tmp_path):
 (tmp_path/"target.txt").touch();vals={"a":admission(tmp_path),"q":observation_request(root=tmp_path)};monkeypatch.setattr(cli,"_read",vals.get);x,c=cli.run(["--admission","a","--observation-request","q"]);assert c==0 and validate(x).valid
