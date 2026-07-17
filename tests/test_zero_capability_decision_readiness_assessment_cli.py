from cli import zero_capability_decision_readiness_assessment as cli
from core.runtime.runtime_capability_decision_readiness_assessment_validation import validate_capability_decision_readiness_assessment as validate
from tests.test_runtime_capability_observation_evidence_consumer_acceptance import acceptance
from tests.test_runtime_capability_observation_evidence_relevance_assessment import relevance
from tests.test_runtime_capability_observation_evidence_sufficiency_assessment import sufficiency
from tests.test_runtime_capability_observation_evidence_closure import closure
def test_cli(monkeypatch,tmp_path):
 (tmp_path/"target.txt").touch();vals={"a":acceptance(tmp_path),"r":relevance(tmp_path),"s":sufficiency(tmp_path),"c":closure(tmp_path)};monkeypatch.setattr(cli,"_read",vals.__getitem__);x,code=cli.run(["--acceptance","a","--relevance","r","--sufficiency","s","--observation-closure","c"]);assert code==0 and validate(x).valid
