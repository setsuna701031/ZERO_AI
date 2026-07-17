from cli import zero_capability_bounded_decision_review_request as cli
from core.runtime.runtime_capability_bounded_decision_review_request_validation import validate_capability_bounded_decision_review_request as validate
from tests.test_runtime_capability_bounded_decision_review_request import proposal,permissions
from tests.test_runtime_capability_decision_readiness_closure import decision_closure
def test_cli(monkeypatch,tmp_path):
 (tmp_path/"target.txt").touch();c=decision_closure(tmp_path);vals={"c":c,"p":proposal(c),"s":c["decision_question"]["decision_scope"],"m":permissions()};monkeypatch.setattr(cli,"_read",vals.__getitem__);x,code=cli.run(["--readiness-closure","c","--decision-proposal","p","--requested-scope","s","--requested-permissions","m","--requested-effect-class","none"]);assert code==0 and validate(x).valid;monkeypatch.setattr(cli,"_read",lambda p:(_ for _ in ()).throw(OSError("missing")));assert cli.run(["--readiness-closure","c","--decision-proposal","p","--requested-scope","s","--requested-permissions","m","--requested-effect-class","none"])[1]==2
