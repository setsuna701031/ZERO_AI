from __future__ import annotations
from typing import Any,Mapping,Protocol
from core.engineering.engineering_governed_explicit_commit import NO_AUTHORITY
from core.engineering.engineering_governed_explicit_pull_request import CLOSURE_SCHEMA as PR_CLOSURE_SCHEMA
from core.engineering.engineering_governed_explicit_push import SHA_RE
from core.engineering.engineering_multifile_coding_workflow import canon
from core.engineering.engineering_practical_task_runner import _ref

PREPARATION_SCHEMA="zero.engineering.merge_preparation.v1";REMOTE_SCHEMA="zero.engineering.merge_remote_verification.v1";ELIGIBILITY_SCHEMA="zero.engineering.merge_eligibility.v1";REVIEW_SCHEMA="zero.engineering.merge_review.v1";AUTH_SCHEMA="zero.engineering.merge_authorization.v1";REQUEST_SCHEMA="zero.engineering.merge_execution_request.v1";EXECUTION_SCHEMA="zero.engineering.merge_execution_result.v1";EVIDENCE_SCHEMA="zero.engineering.merge_evidence.v1";POST_SCHEMA="zero.engineering.merge_post_verification.v1";CLOSURE_SCHEMA="zero.engineering.merge_closure.v1"
STORE_FILES={"preparation":"merge/preparation.json","remote":"merge/remote-verification.json","eligibility":"merge/eligibility.json","review":"merge/review.json","authorization":"merge/authorization.json","request":"merge/execution-request.json","execution":"merge/execution-result.json","evidence":"merge/evidence.json","post":"merge/post-verification.json","closure":"merge/closure.json"}
MERGE_AUTHORITY={**NO_AUTHORITY,"may_merge":True}
class GovernedMergeError(ValueError):
 def __init__(self,code):super().__init__(code);self.code=code
class MergeProviderAdapter(Protocol):
 provider_name:str
 def inspect_merge(self,repository_owner:str,repository_name:str,provider_pr_id:str)->Mapping[str,Any]:...
 def perform_merge(self,request:Mapping[str,Any])->Mapping[str,Any]:...
 def inspect_merge_result(self,repository_owner:str,repository_name:str,provider_pr_id:str)->Mapping[str,Any]:...
def _integrity(a,fp,id,prefix):
 b={k:v for k,v in a.items() if k not in {fp,id}};r=canon(b,fp,id,prefix);return r.get(fp)==a.get(fp) and r.get(id)==a.get(id)
def validate_pr_closure(c):
 e=[]
 if c.get("schema")!=PR_CLOSURE_SCHEMA:e.append("invalid_pr_closure_schema")
 if not _integrity(c,"pull_request_closure_fingerprint","pull_request_closure_id","engineering-pr-closure-"):e.append("pr_closure_fingerprint_invalid")
 if c.get("sealed") is not True or c.get("closure_status")!="awaiting_merge_review":e.append("pr_closure_not_awaiting_merge_review")
 if c.get("merged") or c.get("closed") or c.get("observed_pr_state")!="open":e.append("pr_closure_state_invalid")
 for k in ("pull_request_closure_id","repository_provider","repository_id","remote_url","provider_pr_id","source_branch","target_branch","source_commit_sha","target_commit_sha"):
  if not c.get(k):e.append("pr_closure_missing_"+k)
 return sorted(set(e))
def build_merge_preparation(c,*,repository_owner,repository_name,merge_method="merge_commit"):
 e=validate_pr_closure(c)
 if merge_method!="merge_commit":e.append("unsupported_merge_method")
 p={"schema":PREPARATION_SCHEMA,"pr_closure_id":c.get("pull_request_closure_id"),"repository_provider":c.get("repository_provider"),"repository_id":c.get("repository_id"),"repository_owner":repository_owner,"repository_name":repository_name,"remote_url":c.get("remote_url"),"provider_pr_id":c.get("provider_pr_id"),"source_branch":c.get("source_branch"),"target_branch":c.get("target_branch"),"source_commit_sha":c.get("source_commit_sha"),"target_commit_sha":c.get("target_commit_sha"),"merge_method":merge_method,"preparation_status":"prepared" if not e else "blocked","reason_codes":e,"authority":NO_AUTHORITY}
 return canon(p,"merge_preparation_fingerprint","merge_preparation_id","engineering-merge-preparation-")
def verify_merge_remote(p,adapter):
 e=[]
 if p.get("preparation_status")!="prepared":e.append("preparation_not_ready")
 if adapter.provider_name!=p.get("repository_provider"):e.append("provider_mismatch")
 o=dict(adapter.inspect_merge(p["repository_owner"],p["repository_name"],p["provider_pr_id"]))
 checks={"repository_id":"repository_identity_mismatch","provider_pr_id":"provider_pr_identity_mismatch","source_branch":"source_branch_mismatch","target_branch":"target_branch_mismatch","source_head":"source_head_drift","target_head":"target_head_drift"}
 expected={"repository_id":p.get("repository_id"),"provider_pr_id":p.get("provider_pr_id"),"source_branch":p.get("source_branch"),"target_branch":p.get("target_branch"),"source_head":p.get("source_commit_sha"),"target_head":p.get("target_commit_sha")}
 for k,r in checks.items():
  if o.get(k)!=expected[k]:e.append(r)
 if not o.get("exists"):e.append("pr_missing")
 if o.get("state")!="open":e.append("pr_not_open")
 if o.get("merged"):e.append("pr_already_merged")
 if o.get("closed"):e.append("pr_closed")
 if not o.get("source_exists") or not o.get("target_exists"):e.append("branch_missing")
 if not o.get("has_changes"):e.append("no_remaining_changes")
 if o.get("conflict_status")=="conflicting":e.append("known_merge_conflict")
 if o.get("conflict_status") not in {"clean","conflicting"}:e.append("merge_eligibility_unknown")
 x={"schema":REMOTE_SCHEMA,"merge_preparation_reference":_ref(p),"pr_closure_id":p.get("pr_closure_id"),"repository_id":o.get("repository_id"),"provider_pr_id":o.get("provider_pr_id"),"source_branch":o.get("source_branch"),"target_branch":o.get("target_branch"),"source_remote_head":o.get("source_head"),"target_remote_head":o.get("target_head"),"source_commit_sha":p.get("source_commit_sha"),"target_commit_sha":p.get("target_commit_sha"),"merge_method":p.get("merge_method"),"has_changes":bool(o.get("has_changes")),"conflict_status":o.get("conflict_status"),"verification_status":"verified" if not e else "failed","reason_codes":sorted(set(e)),"mutation_performed":False,"authority":NO_AUTHORITY}
 return canon(x,"merge_remote_verification_fingerprint","merge_remote_verification_id","engineering-merge-remote-")
def evaluate_merge_eligibility(p,r):
 e=[]
 if r.get("verification_status")!="verified" or r.get("merge_preparation_reference")!=_ref(p):e.append("remote_verification_invalid")
 if r.get("pr_closure_id")!=p.get("pr_closure_id"):e.append("pr_closure_id_mismatch")
 if p.get("merge_method")!="merge_commit":e.append("unsupported_merge_method")
 if not r.get("has_changes"):e.append("no_remaining_changes")
 if r.get("conflict_status")!="clean":e.append("merge_not_proven_clean")
 x={"schema":ELIGIBILITY_SCHEMA,"merge_preparation_reference":_ref(p),"remote_verification_reference":_ref(r),"pr_closure_id":p.get("pr_closure_id"),"decision":"eligible" if not e else "ineligible","reason_codes":sorted(set(e)),"approval_granted":False,"authority":NO_AUTHORITY}
 return canon(x,"merge_eligibility_fingerprint","merge_eligibility_id","engineering-merge-eligibility-")
def review_merge(p,r,elig,review):
 if not review.get("human_actor"):raise GovernedMergeError("missing_human_review")
 if review.get("decision") not in {"approved","rejected","blocked"}:raise GovernedMergeError("invalid_review_decision")
 e=[]
 if elig.get("decision")!="eligible":e.append("merge_not_eligible")
 if any(x.get("pr_closure_id")!=p.get("pr_closure_id") for x in (r,elig)):e.append("pr_closure_id_mismatch")
 d=review["decision"] if not e else "blocked"
 x={"schema":REVIEW_SCHEMA,"merge_preparation_reference":_ref(p),"merge_eligibility_reference":_ref(elig),"pr_closure_id":p.get("pr_closure_id"),"merge_preparation_id":p.get("merge_preparation_id"),"merge_preparation_fingerprint":p.get("merge_preparation_fingerprint"),"merge_eligibility_id":elig.get("merge_eligibility_id"),"repository_id":p.get("repository_id"),"provider_pr_id":p.get("provider_pr_id"),"source_branch":p.get("source_branch"),"target_branch":p.get("target_branch"),"source_remote_head":r.get("source_remote_head"),"target_remote_head":r.get("target_remote_head"),"source_commit_sha":p.get("source_commit_sha"),"target_commit_sha":p.get("target_commit_sha"),"merge_method":p.get("merge_method"),"human_actor":review["human_actor"],"decision":d,"reason_codes":e,"authority":NO_AUTHORITY}
 return canon(x,"merge_review_fingerprint","merge_review_id","engineering-merge-review-")
def authorize_merge(p,r,elig,review,a):
 if not a.get("human_actor"):raise GovernedMergeError("missing_authorization")
 e=[]
 if review.get("decision")!="approved":e.append("review_not_approved")
 if review.get("merge_preparation_reference")!=_ref(p) or review.get("merge_eligibility_reference")!=_ref(elig):e.append("review_reference_mismatch")
 scope=a.get("scope") or {};expected={"provider":p.get("repository_provider"),"repository_id":p.get("repository_id"),"provider_pr_id":p.get("provider_pr_id"),"source_branch":p.get("source_branch"),"target_branch":p.get("target_branch"),"source_head":r.get("source_remote_head"),"target_head":r.get("target_remote_head"),"merge_method":"merge_commit","pr_closure_id":p.get("pr_closure_id"),"attempts":1}
 if scope!=expected:e.append("authorization_scope_mismatch")
 ok=a.get("decision")=="authorized" and not e
 x={"schema":AUTH_SCHEMA,"merge_preparation_reference":_ref(p),"remote_verification_reference":_ref(r),"merge_eligibility_reference":_ref(elig),"merge_review_reference":_ref(review),"pr_closure_id":p.get("pr_closure_id"),"human_actor":a["human_actor"],"decision":a.get("decision"),"authorized":ok,"scope":scope,"usage_status":"unused","use_count":0,"reason_codes":e,"authority":MERGE_AUTHORITY if ok else NO_AUTHORITY}
 return canon(x,"merge_authorization_fingerprint","merge_authorization_id","engineering-merge-authorization-")
def build_merge_request(p,r,elig,review,a):
 e=[]
 if elig.get("decision")!="eligible":e.append("merge_not_eligible")
 if review.get("decision")!="approved":e.append("review_not_approved")
 if not a.get("authorized") or a.get("usage_status")!="unused":e.append("authorization_not_available")
 if any(x.get("pr_closure_id")!=p.get("pr_closure_id") for x in (r,elig,review,a)):e.append("pr_closure_id_mismatch")
 x={"schema":REQUEST_SCHEMA,"merge_preparation_reference":_ref(p),"remote_verification_reference":_ref(r),"merge_eligibility_reference":_ref(elig),"merge_review_reference":_ref(review),"merge_authorization_reference":_ref(a),"pr_closure_id":p.get("pr_closure_id"),"repository_provider":p.get("repository_provider"),"repository_id":p.get("repository_id"),"repository_owner":p.get("repository_owner"),"repository_name":p.get("repository_name"),"provider_pr_id":p.get("provider_pr_id"),"source_branch":p.get("source_branch"),"target_branch":p.get("target_branch"),"source_head":r.get("source_remote_head"),"target_head":r.get("target_remote_head"),"merge_method":p.get("merge_method"),"request_status":"ready" if not e else "blocked","reason_codes":e,"authority":NO_AUTHORITY}
 return canon(x,"merge_execution_request_fingerprint","merge_execution_request_id","engineering-merge-request-")
def execute_merge(c,p,r,elig,review,a,req,adapter):
 e=validate_pr_closure(c)
 if c.get("pull_request_closure_id")!=p.get("pr_closure_id"):e.append("pr_closure_id_mismatch")
 if not _integrity(p,"merge_preparation_fingerprint","merge_preparation_id","engineering-merge-preparation-"):e.append("preparation_integrity_invalid")
 if elig.get("decision")!="eligible":e.append("merge_not_eligible")
 if review.get("decision")!="approved":e.append("review_not_approved")
 if not a.get("authorized") or a.get("usage_status")!="unused":e.append("authorization_not_available")
 if req.get("request_status")!="ready" or req.get("merge_authorization_reference")!=_ref(a):e.append("request_not_ready")
 now=verify_merge_remote(p,adapter)
 if now.get("verification_status")!="verified":e.extend(now.get("reason_codes") or [])
 if now.get("source_remote_head")!=r.get("source_remote_head"):e.append("source_head_changed")
 if now.get("target_remote_head")!=r.get("target_remote_head"):e.append("target_head_changed")
 if e:raise GovernedMergeError(sorted(set(e))[0])
 used={**a,"usage_status":"consumed","use_count":1}
 try:out=dict(adapter.perform_merge({k:req[k] for k in ("repository_provider","repository_id","repository_owner","repository_name","provider_pr_id","source_branch","target_branch","source_head","target_head","merge_method")}));provider_error=None
 except Exception as exc:out={};provider_error=type(exc).__name__
 status="merged" if out.get("merged") and out.get("merge_commit_sha") else "failed"
 x={"schema":EXECUTION_SCHEMA,"merge_execution_request_reference":_ref(req),"pr_closure_id":p.get("pr_closure_id"),"provider_pr_id":p.get("provider_pr_id"),"merge_commit_sha":out.get("merge_commit_sha"),"provider_state":out.get("state"),"provider_error":provider_error,"execution_status":status,"attempt_count":1,"retry_performed":False,"source_branch_deleted":False,"authority":NO_AUTHORITY}
 return used,canon(x,"merge_execution_fingerprint","merge_execution_id","engineering-merge-execution-")
def build_merge_evidence(p,r,elig,review,a,exe,adapter):
 o=dict(adapter.inspect_merge_result(p["repository_owner"],p["repository_name"],p["provider_pr_id"]));x={"schema":EVIDENCE_SCHEMA,"pr_closure_id":p.get("pr_closure_id"),"preparation_id":p.get("merge_preparation_id"),"eligibility_id":elig.get("merge_eligibility_id"),"review_id":review.get("merge_review_id"),"authorization_id":a.get("merge_authorization_id"),"execution_result_id":exe.get("merge_execution_id"),"provider":p.get("repository_provider"),"repository_id":p.get("repository_id"),"provider_pr_id":p.get("provider_pr_id"),"source_branch":p.get("source_branch"),"target_branch":p.get("target_branch"),"pre_merge_source_head":r.get("source_remote_head"),"pre_merge_target_head":r.get("target_remote_head"),"merge_commit_sha":o.get("merge_commit_sha"),"post_merge_target_head":o.get("target_head"),"merge_method":p.get("merge_method"),"provider_merge_state":o.get("state"),"evidence_status":"observed" if exe.get("execution_status")=="merged" else "failed","authority":NO_AUTHORITY};return canon(x,"merge_evidence_fingerprint","merge_evidence_id","engineering-merge-evidence-")
def verify_merged(p,exe,ev,adapter):
 o=dict(adapter.inspect_merge_result(p["repository_owner"],p["repository_name"],p["provider_pr_id"]));e=[]
 if not o.get("merged") or o.get("state")!="merged":e.append("merge_not_proven")
 for k,v,r in (("repository_id",p.get("repository_id"),"repository_mismatch"),("provider_pr_id",p.get("provider_pr_id"),"pr_mismatch"),("source_branch",p.get("source_branch"),"source_branch_mismatch"),("target_branch",p.get("target_branch"),"target_branch_mismatch"),("merge_method","merge_commit","merge_method_mismatch"),("merge_commit_sha",exe.get("merge_commit_sha"),"merge_commit_mismatch")):
  if o.get(k)!=v:e.append(r)
 if o.get("target_head")!=exe.get("merge_commit_sha"):e.append("target_head_not_merge_commit")
 if not o.get("source_reachable"):e.append("source_not_reachable")
 if o.get("source_deleted"):e.append("source_branch_deleted")
 if o.get("unrelated_branch_changed"):e.append("unrelated_branch_changed")
 x={"schema":POST_SCHEMA,"merge_evidence_reference":_ref(ev),"pr_closure_id":p.get("pr_closure_id"),"provider_pr_id":p.get("provider_pr_id"),"merge_commit_sha":o.get("merge_commit_sha"),"post_merge_target_head":o.get("target_head"),"source_reachable":bool(o.get("source_reachable")),"source_branch_deleted":bool(o.get("source_deleted")),"verification_status":"verified" if not e else "failed","reason_codes":sorted(set(e)),"authority":NO_AUTHORITY};return canon(x,"merge_post_verification_fingerprint","merge_post_verification_id","engineering-merge-post-")
def close_merge(p,r,elig,review,a,exe,ev,post):
 e=[];cid=p.get("pr_closure_id")
 if any(x.get("pr_closure_id")!=cid for x in (r,elig,review,a,exe,ev,post)):e.append("pr_closure_id_mismatch")
 if a.get("usage_status")!="consumed" or a.get("use_count")!=1:e.append("authorization_not_consumed_once")
 if post.get("verification_status")!="verified":e.append("post_verification_failed")
 x={"schema":CLOSURE_SCHEMA,"pr_closure_id":cid,"merge_preparation_id":p.get("merge_preparation_id"),"remote_verification_id":r.get("merge_remote_verification_id"),"eligibility_id":elig.get("merge_eligibility_id"),"review_id":review.get("merge_review_id"),"authorization_id":a.get("merge_authorization_id"),"execution_result_id":exe.get("merge_execution_id"),"evidence_id":ev.get("merge_evidence_id"),"post_verification_id":post.get("merge_post_verification_id"),"provider_pr_id":p.get("provider_pr_id"),"repository_id":p.get("repository_id"),"source_branch":p.get("source_branch"),"target_branch":p.get("target_branch"),"source_commit_sha":p.get("source_commit_sha"),"pre_merge_target_sha":r.get("target_remote_head"),"merge_commit_sha":exe.get("merge_commit_sha"),"post_merge_target_sha":post.get("post_merge_target_head"),"merge_method":p.get("merge_method"),"sealed":not e,"closure_status":"merged_verified" if not e else "failed","released":False,"tagged":False,"deployed":False,"source_branch_deleted":False,"reason_codes":e,"authority":NO_AUTHORITY};return canon(x,"merge_closure_fingerprint","merge_closure_id","engineering-merge-closure-")
def inspect_merge_state(b):
 g=lambda k:b.get(STORE_FILES[k]) or {};return {"schema":"zero.engineering.merge_state.v1","preparation_status":g("preparation").get("preparation_status","not_started"),"remote_status":g("remote").get("verification_status","not_started"),"eligibility":g("eligibility").get("decision","not_started"),"review":g("review").get("decision","not_started"),"authorized":bool(g("authorization").get("authorized")),"execution":g("execution").get("execution_status","not_started"),"closure":g("closure").get("closure_status","not_started"),**{f"will_{x}":False for x in ("merge","retry","auto_merge","delete_branch","tag","release","deploy","workflow")}}
