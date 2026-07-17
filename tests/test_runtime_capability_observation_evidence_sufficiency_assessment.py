from copy import deepcopy
from core.runtime.runtime_capability_observation_evidence_sufficiency_assessment import build_capability_observation_evidence_sufficiency_assessment as build
from tests.test_runtime_capability_observation_evidence_relevance_assessment import relevance
from tests.test_runtime_capability_observation_evidence_consumer_acceptance import acceptance
from tests.test_runtime_capability_observation_evidence_closure import closure
from tests.test_runtime_capability_read_only_observation_result import result
def requirements(**kw):return {"require_observed":True,"require_not_truncated":False,"require_target_type":False,"require_nonempty_evidence":True,**kw}
def sufficiency(root,req=None):return build(relevance(root),acceptance(root),closure(root),result(root),sufficiency_requirements=requirements() if req is None else req)
def test_sufficiency_and_truncation(tmp_path):
 (tmp_path/"target.txt").touch();assert sufficiency(tmp_path)["sufficiency_status"]=="sufficient" and sufficiency(tmp_path)==sufficiency(tmp_path)
 r=result(tmp_path);r=deepcopy(r);r["truncated"]=True;assert build(relevance(tmp_path),acceptance(tmp_path),closure(tmp_path),r,sufficiency_requirements=requirements(require_not_truncated=True))["sufficiency_status"] in {"insufficient","invalid"}
 assert build(relevance(tmp_path),acceptance(tmp_path),closure(tmp_path),result(tmp_path),sufficiency_requirements={"require_observed":True})["sufficiency_status"]=="invalid"
