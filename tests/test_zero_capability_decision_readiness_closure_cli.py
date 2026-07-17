from cli import zero_capability_decision_readiness_closure as cli
from core.runtime.runtime_capability_decision_readiness_closure_validation import validate_capability_decision_readiness_closure as validate
from tests.test_runtime_capability_execution_authority import authority
from tests.test_runtime_capability_bounded_execution_request import request
from tests.test_runtime_capability_observation_evidence_closure import closure
from tests.test_runtime_capability_observation_evidence_consumer_acceptance import acceptance
from tests.test_runtime_capability_observation_evidence_relevance_assessment import relevance
from tests.test_runtime_capability_observation_evidence_sufficiency_assessment import sufficiency
from tests.test_runtime_capability_decision_readiness_assessment import readiness
from tests.test_runtime_capability_decision_readiness_closure import bridge
def test_cli(monkeypatch,tmp_path):
 (tmp_path/"target.txt").touch();vals=dict(zip("aebocrsd",(authority(),request(),bridge(tmp_path),closure(tmp_path),acceptance(tmp_path),relevance(tmp_path),sufficiency(tmp_path),readiness(tmp_path))));monkeypatch.setattr(cli,"_read",vals.__getitem__);args=[]
 for n,v in zip(("authority","execution-request","bridge-closure","observation-closure","acceptance","relevance","sufficiency","readiness"),vals):args += ["--"+n,v]
 x,code=cli.run(args);assert code==0 and validate(x).valid
