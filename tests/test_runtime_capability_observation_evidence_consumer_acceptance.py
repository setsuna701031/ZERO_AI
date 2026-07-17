from copy import deepcopy
from core.runtime.runtime_capability_observation_evidence_consumer_acceptance import build_capability_observation_evidence_consumer_acceptance as build
from tests.test_runtime_capability_observation_evidence_closure import closure
from tests.test_runtime_capability_read_only_observation_result import result
def evidence(root):return closure(root),result(root)
def acceptance(root):return build(*evidence(root))
def test_acceptance_and_tampering(tmp_path):
 (tmp_path/"target.txt").touch();x=acceptance(tmp_path);assert x["acceptance_status"]=="accepted" and x==acceptance(tmp_path)
 c,r=evidence(tmp_path);c=deepcopy(c);c["observation_closure_fingerprint"]="bad";assert build(c,r)["acceptance_status"]=="invalid"
 r=deepcopy(r);r["side_effects_performed"]=["effect"];assert build(closure(tmp_path),r)["acceptance_status"]=="invalid"
