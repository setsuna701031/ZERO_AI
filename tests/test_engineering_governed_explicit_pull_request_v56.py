from __future__ import annotations
import copy, subprocess, sys
from pathlib import Path
import pytest
from core.engineering.engineering_governed_explicit_pull_request import *
from core.engineering.engineering_multifile_coding_workflow import canon
from core.engineering.engineering_runtime_session_store import read_session_artifact,write_session_artifact

def closure():
 body={"schema":"zero.engineering.push_closure.v1","push_closure_id":"temporary","commit_verification_closure_id":"cv","push_preparation_reference":{},"push_authorization_reference":{},"push_execution_reference":{},"push_evidence_reference":{},"remote_verification_reference":{},"target_commit":"a"*40,"remote_commit":"a"*40,"repository_id":"repo-1","remote_name":"origin","remote_url":"https://example.invalid/o/r.git","source_branch":"feature","pushed_commit_sha":"a"*40,"verified_remote_commit_sha":"a"*40,"closed_at":"t","closure_status":"closed","sealed":True,"reason_codes":[],"next_governed_action":"push_complete","no_pr_created":True,"no_merge_performed":True,"no_tag_created":True,"no_release_created":True,"authority":NO_AUTHORITY}
 body.pop("push_closure_id");return canon(body,"push_closure_fingerprint","push_closure_id","engineering-push-closure-")

class Provider:
 provider_name="fixture"
 def __init__(self):self.source="a"*40;self.target="b"*40;self.created={};self.calls=0;self.equivalent=None;self.fail=False
 def inspect_repository(self,o,n):return {"repository_id":"repo-1","remote_url":"https://example.invalid/o/r.git"}
 def inspect_branches(self,o,n,s,t,c):return {"source_exists":self.source is not None,"target_exists":self.target is not None,"source_head":self.source,"target_head":self.target,"source_commit_ancestor":self.source==c,"has_changes":self.source!=self.target}
 def find_equivalent_open_pull_request(self,o,n,s,t):return self.equivalent
 def create_pull_request(self,r):
  self.calls+=1
  if self.fail:return {"created":False,"status":"failed"}
  self.created={"provider_pr_id":"pr-1","pr_number":1,"pr_url":"https://example.invalid/o/r/pr/1","created":True,"status":"open",**r};return self.created
 def inspect_pull_request(self,o,n,p):return {"provider_pr_id":p,"repository_id":"repo-1","source_branch":"feature","target_branch":"main","source_commit_sha":"a"*40,"source_head":self.source,"target_head":self.target,"state":"open","merged":False,"closed":False}

def chain(provider=None):
 p=provider or Provider();c=closure();prep=build_pr_preparation(c,repository_provider="fixture",repository_id="repo-1",repository_owner="o",repository_name="r",remote_name="origin",remote_url="https://example.invalid/o/r.git",source_branch="feature",target_branch="main",target_commit_sha="b"*40,title="Feature",body="Body")
 adm=admit_repository_provider(prep,p);remote=verify_pr_remote(prep,adm,p);review=review_pull_request(prep,remote,{"human_actor":"reviewer","decision":"approved"})
 scope={"provider":"fixture","repository_id":"repo-1","source_branch":"feature","target_branch":"main","source_commit_sha":"a"*40,"title_fingerprint":prep["title_fingerprint"],"body_fingerprint":prep["body_fingerprint"],"attempts":1}
 auth=authorize_pull_request(prep,remote,review,{"human_actor":"authorizer","decision":"authorized","scope":scope});req=build_pr_creation_request(prep,remote,review,auth)
 return p,c,prep,adm,remote,review,auth,req

def test_successful_governed_fixture_pr_and_awaiting_merge_closure():
 p,c,prep,adm,remote,review,auth,req=chain();used,exe=execute_pull_request(c,prep,adm,remote,review,auth,req,p);ev=build_pr_evidence(prep,review,used,exe,p);post=verify_created_pull_request(prep,exe,ev,p);closed=close_pull_request(prep,remote,review,used,exe,ev,post)
 assert p.calls==1 and ev["evidence_status"]=="complete" and post["verification_status"]=="verified"
 assert closed["closure_status"]=="awaiting_merge_review" and closed["sealed"] and not closed["merge_authorized"] and not closed["merged"]
 assert all(x["push_closure_id"]==c["push_closure_id"] for x in (prep,adm,remote,review,used,req,exe,ev,post,closed))

def test_sealed_push_closure_and_integrity_required():
 p=Provider();c=closure();bad={**c,"sealed":False};prep=build_pr_preparation(bad,repository_provider="fixture",repository_id="repo-1",repository_owner="o",repository_name="r",remote_name="origin",remote_url=c["remote_url"],source_branch="feature",target_branch="main",target_commit_sha="b"*40,title="T",body="")
 assert prep["preparation_status"]=="blocked" and "push_closure_not_successful" in prep["reason_codes"]
 tamper={**c,"reason_codes":["tampered"]};assert "push_closure_fingerprint_invalid" in validate_push_closure(tamper)

def test_push_closure_id_and_source_commit_substitution_rejected():
 p,c,prep,adm,remote,review,auth,req=chain();changed={**prep,"push_closure_id":"other"}
 with pytest.raises(GovernedPullRequestError):execute_pull_request(c,changed,adm,remote,review,auth,req,p)
 wrong=build_pr_preparation(c,repository_provider="fixture",repository_id="repo-1",repository_owner="o",repository_name="r",remote_name="origin",remote_url=c["remote_url"],source_branch="other",target_branch="main",target_commit_sha="b"*40,title="T",body="")
 assert wrong["preparation_status"]=="blocked"

@pytest.mark.parametrize(("field","reason"),[("source","source_branch_missing"),("target","target_branch_missing")])
def test_missing_branches(field,reason):
 p=Provider();setattr(p,field,None);_,_,prep,adm,*_=chain(p);assert reason in verify_pr_remote(prep,adm,p)["reason_codes"]

def test_equal_branches_and_no_changes_fail_closed():
 c=closure();prep=build_pr_preparation(c,repository_provider="fixture",repository_id="repo-1",repository_owner="o",repository_name="r",remote_name="origin",remote_url=c["remote_url"],source_branch="main",target_branch="main",target_commit_sha="b"*40,title="T",body="")
 assert "source_target_branch_equal" in prep["reason_codes"]
 p=Provider();p.target=p.source;_,_,prep,adm,*_=chain(p);assert "no_changes" in verify_pr_remote(prep,adm,p)["reason_codes"]

def test_branch_freeze_after_review():
 p,c,prep,adm,remote,review,auth,req=chain();p.source="c"*40
 with pytest.raises(GovernedPullRequestError,match="source_branch_changed|source_head_mismatch"):execute_pull_request(c,prep,adm,remote,review,auth,req,p)

def test_target_freeze_after_review():
 p,c,prep,adm,remote,review,auth,req=chain();p.target="c"*40
 with pytest.raises(GovernedPullRequestError,match="target_branch_changed|target_head_mismatch"):execute_pull_request(c,prep,adm,remote,review,auth,req,p)

@pytest.mark.parametrize("decision",["rejected","blocked"])
def test_review_not_approved(decision):
 p,c,prep,adm,remote,_,_,_=chain();review=review_pull_request(prep,remote,{"human_actor":"r","decision":decision});auth=authorize_pull_request(prep,remote,review,{"human_actor":"a","decision":"authorized","scope":{}});assert not auth["authorized"]

def test_review_and_authorization_required_scope_and_reuse():
 p,c,prep,adm,remote,review,auth,req=chain();bad=authorize_pull_request(prep,remote,review,{"human_actor":"a","decision":"authorized","scope":{}});assert not bad["authorized"]
 with pytest.raises(GovernedPullRequestError):execute_pull_request(c,prep,adm,remote,review,bad,req,p)
 used,exe=execute_pull_request(c,prep,adm,remote,review,auth,req,p)
 with pytest.raises(GovernedPullRequestError,match="authorization_not_available"):execute_pull_request(c,prep,adm,remote,review,used,req,p)

def test_title_body_repository_and_remote_substitution_rejected():
 p,c,prep,adm,remote,review,auth,req=chain();changed={**req,"title":"Other"}
 with pytest.raises(GovernedPullRequestError,match="title_body_substitution"):execute_pull_request(c,prep,adm,remote,review,auth,changed,p)
 for kwargs,reason in [({"repository_id":"other"},"repository_identity_mismatch"),({"remote_url":"x"},"remote_identity_mismatch")]:
  values={"repository_provider":"fixture","repository_id":"repo-1","repository_owner":"o","repository_name":"r","remote_name":"origin","remote_url":c["remote_url"],"source_branch":"feature","target_branch":"main","target_commit_sha":"b"*40,"title":"T","body":"",**kwargs};assert reason in build_pr_preparation(c,**values)["reason_codes"]

def test_equivalent_pr_and_provider_failure_do_not_retry():
 p=Provider();p.equivalent={"provider_pr_id":"existing"};_,_,prep,adm,*_=chain(p);assert "equivalent_open_pull_request" in verify_pr_remote(prep,adm,p)["reason_codes"]
 p,c,prep,adm,remote,review,auth,req=chain();p.fail=True;used,exe=execute_pull_request(c,prep,adm,remote,review,auth,req,p);assert exe["execution_status"]=="failed" and exe["attempt_count"]==1 and not exe["retry_performed"] and p.calls==1

def test_session_store_and_no_merge_cli_surface(tmp_path):
 for name in STORE_FILES.values():write_session_artifact(tmp_path,"s56",name,{"schema":"test"});assert read_session_artifact(tmp_path,"s56",name)=={"schema":"test"}
 cp=subprocess.run([sys.executable,"-m","cli.zero_engineering_runtime_pull_request","--help"],cwd=Path(__file__).parents[1],text=True,capture_output=True);assert cp.returncode==0
 for forbidden in ("merge","retry","label","reviewer","milestone","workflow"):assert forbidden not in cp.stdout
