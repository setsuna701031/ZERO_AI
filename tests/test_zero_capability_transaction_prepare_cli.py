from cli import zero_capability_transaction_prepare as cli
from core.runtime.runtime_capability_transaction_preparation_integration_closure_validation import validate_capability_transaction_preparation_integration_closure as validate
from tests.test_runtime_capability_decision_transaction_preparation import inputs
def test_cli(monkeypatch,tmp_path):
 (tmp_path/"target.txt").touch();monkeypatch.setattr(cli,"_read",lambda _:inputs(tmp_path));x,code=cli.run(["--bundle","bundle"]);assert code==0 and validate(x["integration_closure"]).valid
 monkeypatch.setattr(cli,"_read",lambda _:(_ for _ in ()).throw(OSError("missing")));assert cli.run(["--bundle","missing"])[1]==2
