from cli import zero_capability_observation_evidence_consumer_acceptance as cli
from core.runtime.runtime_capability_observation_evidence_consumer_acceptance_validation import validate_capability_observation_evidence_consumer_acceptance as validate
from tests.test_runtime_capability_observation_evidence_consumer_acceptance import evidence
def test_cli(monkeypatch,tmp_path):
 (tmp_path/"target.txt").touch();c,x=evidence(tmp_path);vals={"c":c,"x":x};monkeypatch.setattr(cli,"_read",vals.__getitem__);a,code=cli.run(["--observation-closure","c","--observation-result","x"]);assert code==0 and validate(a).valid
 monkeypatch.setattr(cli,"_read",lambda p:(_ for _ in ()).throw(OSError("missing")));assert cli.run(["--observation-closure","c","--observation-result","x"])[1]==2
