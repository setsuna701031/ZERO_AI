import json
from cli import zero_capability_bounded_observation_request as cli
from core.runtime.runtime_capability_bounded_observation_request_validation import validate_capability_bounded_observation_request as validate
from tests.test_runtime_capability_read_only_adapter_admission import admission
from tests.test_runtime_capability_bounded_execution_request import request
from tests.test_runtime_capability_bounded_observation_request import limits
def test_cli(monkeypatch):
 vals={"a":admission(),"r":request(),"l":limits()};monkeypatch.setattr(cli,"_read",vals.get);x,c=cli.run(["--admission","a","--request","r","--observation-kind","existence","--relative-target","x","--limits","l"]);assert c==0 and validate(x).valid
 monkeypatch.setattr(cli,"_read",lambda p:(_ for _ in ()).throw(json.JSONDecodeError("bad","",0)));assert cli.run(["--admission","a","--request","r","--observation-kind","existence","--relative-target","x","--limits","l"])[1]==2
