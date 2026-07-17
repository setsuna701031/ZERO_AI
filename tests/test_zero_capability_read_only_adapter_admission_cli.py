from cli import zero_capability_read_only_adapter_admission as cli
from core.runtime.runtime_capability_read_only_adapter_admission_validation import validate_capability_read_only_adapter_admission as validate
from tests.test_runtime_capability_execution_authority import authority
from tests.test_runtime_capability_bounded_execution_request import request
from tests.test_runtime_capability_executor_bridge_verification_closure import bridge_closure
def test_cli(monkeypatch):
 vals={"a":authority(),"r":request(),"c":bridge_closure()};monkeypatch.setattr(cli,"_read",vals.__getitem__);x,c=cli.run(["--authority","a","--request","r","--bridge-closure","c","--workspace-root","."]);assert c==0 and validate(x).valid
 monkeypatch.setattr(cli,"_read",lambda p:(_ for _ in ()).throw(OSError("missing")));assert cli.run(["--authority","missing","--request","r","--bridge-closure","c","--workspace-root","."])[1]==2
