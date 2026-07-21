from __future__ import annotations
import subprocess,sys
from pathlib import Path
import pytest
from core.engineering.engineering_governed_explicit_merge import *
from core.engineering.engineering_multifile_coding_workflow import canon
from core.engineering.engineering_runtime_session_store import read_session_artifact,write_session_artifact
def closure():
 b={"schema":"zero.engineering.pull_request_closure.v1","push_closure_id":"push","preparation_id":"p","remote_verification_id":"r","review_id":"v","authorization_id":"a","execution_result_id":"x","evidence_id":"e","post_verification_id":"o","provider_pr_id":"pr-1","repository_id":"repo","repository_provider":"fixture","remote_url":"https://example.invalid/o/r.git","source_branch":"feature","target_branch":"main","source_commit_sha":"a"*40,"target_commit_sha":"b"*40,"observed_pr_state":"open","merged":False,"closed":False,"sealed":True,"closure_status":"awaiting_merge_review","reason_codes":[],"merge_authorized":False,"authority":NO_AUTHORITY};return canon(b,"pull_request_closure_fingerprint","pull_request_closure_id","engineering-pr-closure-")
class Provider:
 provider_name="fixture"
 def __init__(self):self.source="a"*40;self.target="b"*40;self.exists=True;self.state="open";self.merged=False;self.closed=False;self.changes=True;self.conflict="clean";self.calls=0;self.fail=False;self.merge_sha="c"*40;self.deleted=False;self.prove=True
 def inspect_merge(self,o,n,p):return {"repository_id":"repo","provider_pr_id":p,"exists":self.exists,"state":self.state,"merged":self.merged,"closed":self.closed,"source_branch":"feature","target_branch":"main","source_exists":self.source is not None,"target_exists":self.target is not None,"source_head":self.source,"target_head":self.target,"has_changes":self.changes,"conflict_status":self.conflict}
 def perform_merge(self,r):
  self.calls+=1;self.merged=not self.fail
  if self.merged:self.state="merged";self.target=self.merge_sha;self.changes=False
  return {"merged":self.merged,"state":self.state,"merge_commit_sha":self.merge_sha if self.merged else None}
 def inspect_merge_result(self,o,n,p):return {"repository_id":"repo","provider_pr_id":p,"source_branch":"feature","target_branch":"main","merged":self.merged and self.prove,"state":"merged" if self.merged and self.prove else "open","merge_method":"merge_commit","merge_commit_sha":self.merge_sha if self.merged else None,"target_head":self.target,"source_reachable":self.merged,"source_deleted":self.deleted,"unrelated_branch_changed":False}
def chain(p=None,method="merge_commit"):
 p=p or Provider();c=closure();prep=build_merge_preparation(c,repository_owner="o",repository_name="r",merge_method=method);remote=verify_merge_remote(prep,p);elig=evaluate_merge_eligibility(prep,remote);review=review_merge(prep,remote,elig,{"human_actor":"r","decision":"approved"});scope={"provider":"fixture","repository_id":"repo","provider_pr_id":"pr-1","source_branch":"feature","target_branch":"main","source_head":"a"*40,"target_head":"b"*40,"merge_method":"merge_commit","pr_closure_id":c["pull_request_closure_id"],"attempts":1};auth=authorize_merge(prep,remote,elig,review,{"human_actor":"a","decision":"authorized","scope":scope});req=build_merge_request(prep,remote,elig,review,auth);return p,c,prep,remote,elig,review,auth,req
def test_successful_fixture_merge_and_sealed_closure():
 p,c,prep,r,e,v,a,q=chain();used,x=execute_merge(c,prep,r,e,v,a,q,p);ev=build_merge_evidence(prep,r,e,v,used,x,p);post=verify_merged(prep,x,ev,p);closed=close_merge(prep,r,e,v,used,x,ev,post);assert p.calls==1 and post["verification_status"]=="verified" and closed["closure_status"]=="merged_verified" and closed["sealed"] and not closed["source_branch_deleted"] and not closed["released"]
def test_sealed_closure_tamper_id_and_status_rejected():
 p=Provider();c=closure()
 for bad in ({**c,"sealed":False},{**c,"reason_codes":["tamper"]},{**c,"closure_status":"other"}):assert build_merge_preparation(bad,repository_owner="o",repository_name="r")["preparation_status"]=="blocked"
 p,c,prep,r,e,v,a,q=chain()
 with pytest.raises(GovernedMergeError):execute_merge(c,{**prep,"pr_closure_id":"other"},r,e,v,a,q,p)
@pytest.mark.parametrize(("field","value","reason"),[("exists",False,"pr_missing"),("closed",True,"pr_closed"),("merged",True,"pr_already_merged"),("changes",False,"no_remaining_changes"),("conflict","conflicting","known_merge_conflict"),("conflict","unknown","merge_eligibility_unknown")])
def test_remote_failures(field,value,reason):
 p=Provider();setattr(p,field,value);_,_,prep,*_=chain(p);assert reason in verify_merge_remote(prep,p)["reason_codes"]
def test_identity_and_branch_mismatch():
 p,c,prep,*_=chain();o=p.inspect_merge;p.inspect_merge=lambda *a:{**o(*a),"repository_id":"other","source_branch":"x","target_branch":"y"};reasons=verify_merge_remote(prep,p)["reason_codes"];assert "repository_identity_mismatch" in reasons and "source_branch_mismatch" in reasons and "target_branch_mismatch" in reasons
def test_source_and_target_drift_after_review():
 p,c,prep,r,e,v,a,q=chain();p.source="d"*40
 with pytest.raises(GovernedMergeError):execute_merge(c,prep,r,e,v,a,q,p)
 p,c,prep,r,e,v,a,q=chain();p.target="d"*40
 with pytest.raises(GovernedMergeError):execute_merge(c,prep,r,e,v,a,q,p)
def test_only_merge_commit_supported():assert "unsupported_merge_method" in chain(method="squash")[2]["reason_codes"]
@pytest.mark.parametrize("decision",["rejected","blocked"])
def test_review_rejected_or_blocked(decision):
 p,c,prep,r,e,_,_,_=chain();v=review_merge(prep,r,e,{"human_actor":"r","decision":decision});a=authorize_merge(prep,r,e,v,{"human_actor":"a","decision":"authorized","scope":{}});assert not a["authorized"]
def test_missing_review_authorization_scope_reuse_and_substitution():
 p,c,prep,r,e,v,a,q=chain()
 with pytest.raises(GovernedMergeError,match="missing_human_review"):review_merge(prep,r,e,{})
 bad=authorize_merge(prep,r,e,v,{"human_actor":"a","decision":"authorized","scope":{}});assert not bad["authorized"]
 used,x=execute_merge(c,prep,r,e,v,a,q,p)
 with pytest.raises(GovernedMergeError):execute_merge(c,prep,r,e,v,used,q,p)
 with pytest.raises(GovernedMergeError):execute_merge(c,prep,r,e,v,{**a,"merge_review_reference":{}},q,p)
def test_provider_failure_no_retry_and_success_without_proof_fails():
 p,c,prep,r,e,v,a,q=chain();p.fail=True;used,x=execute_merge(c,prep,r,e,v,a,q,p);assert x["execution_status"]=="failed" and x["attempt_count"]==1 and not x["retry_performed"] and p.calls==1
 p,c,prep,r,e,v,a,q=chain();used,x=execute_merge(c,prep,r,e,v,a,q,p);p.prove=False;ev=build_merge_evidence(prep,r,e,v,used,x,p);assert verify_merged(prep,x,ev,p)["verification_status"]=="failed"
def test_provider_exception_consumes_authorization_and_never_retries():
 p,c,prep,r,e,v,a,q=chain();p.perform_merge=lambda request:(_ for _ in ()).throw(TimeoutError("timeout"));used,x=execute_merge(c,prep,r,e,v,a,q,p);assert used["usage_status"]=="consumed" and used["use_count"]==1 and x["execution_status"]=="failed" and x["provider_error"]=="TimeoutError" and not x["retry_performed"]
 with pytest.raises(GovernedMergeError,match="authorization_not_available"):execute_merge(c,prep,r,e,v,used,q,p)
def test_post_verifies_commit_target_reachability_and_source_preserved():
 p,c,prep,r,e,v,a,q=chain();used,x=execute_merge(c,prep,r,e,v,a,q,p);ev=build_merge_evidence(prep,r,e,v,used,x,p);assert verify_merged(prep,x,ev,p)["verification_status"]=="verified";p.deleted=True;assert "source_branch_deleted" in verify_merged(prep,x,ev,p)["reason_codes"]
def test_store_and_cli_no_forbidden_surface(tmp_path):
 for n in STORE_FILES.values():write_session_artifact(tmp_path,"s57",n,{"schema":"test"});assert read_session_artifact(tmp_path,"s57",n)=={"schema":"test"}
 cp=subprocess.run([sys.executable,"-m","cli.zero_engineering_runtime_merge","--help"],cwd=Path(__file__).parents[1],text=True,capture_output=True);assert cp.returncode==0
 for forbidden in ("auto-merge","delete-branch","retry","squash","rebase","release","workflow"):assert forbidden not in cp.stdout
 assert "{tag" not in cp.stdout and ",tag" not in cp.stdout
