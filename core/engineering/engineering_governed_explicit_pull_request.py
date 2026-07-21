from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping, Protocol

from core.engineering.engineering_governed_explicit_commit import NO_AUTHORITY
from core.engineering.engineering_governed_explicit_push import CLOSURE_SCHEMA as PUSH_CLOSURE_SCHEMA, BRANCH_RE, SHA_RE
from core.engineering.engineering_multifile_coding_workflow import canon
from core.engineering.engineering_practical_task_runner import _ref

PREPARATION_SCHEMA="zero.engineering.pull_request_preparation.v1"
ADMISSION_SCHEMA="zero.engineering.repository_provider_admission.v1"
REMOTE_SCHEMA="zero.engineering.pull_request_remote_verification.v1"
REVIEW_SCHEMA="zero.engineering.pull_request_review.v1"
AUTH_SCHEMA="zero.engineering.pull_request_authorization.v1"
REQUEST_SCHEMA="zero.engineering.pull_request_creation_request.v1"
EXECUTION_SCHEMA="zero.engineering.pull_request_execution_result.v1"
EVIDENCE_SCHEMA="zero.engineering.pull_request_evidence.v1"
POST_SCHEMA="zero.engineering.pull_request_post_verification.v1"
CLOSURE_SCHEMA="zero.engineering.pull_request_closure.v1"
STORE_FILES={"preparation":"pull-request/preparation.json","admission":"pull-request/provider-admission.json",
 "remote":"pull-request/remote-verification.json","review":"pull-request/review.json","authorization":"pull-request/authorization.json",
 "request":"pull-request/creation-request.json","execution":"pull-request/execution-result.json","evidence":"pull-request/evidence.json",
 "post":"pull-request/post-verification.json","closure":"pull-request/closure.json"}
PR_AUTHORITY={**NO_AUTHORITY,"may_create_pr":True}
SAFE_TEXT=re.compile(r"^[^\x00-\x08\x0b\x0c\x0e-\x1f\x7f]*$")

class GovernedPullRequestError(ValueError):
 def __init__(self,code:str): super().__init__(code); self.code=code

class RepositoryProviderAdapter(Protocol):
 provider_name:str
 def inspect_repository(self,repository_owner:str,repository_name:str)->Mapping[str,Any]:...
 def inspect_branches(self,repository_owner:str,repository_name:str,source_branch:str,target_branch:str,source_commit_sha:str)->Mapping[str,Any]:...
 def find_equivalent_open_pull_request(self,repository_owner:str,repository_name:str,source_branch:str,target_branch:str)->Mapping[str,Any]|None:...
 def create_pull_request(self,request:Mapping[str,Any])->Mapping[str,Any]:...
 def inspect_pull_request(self,repository_owner:str,repository_name:str,provider_pr_id:str)->Mapping[str,Any]:...

def _sha(text:str)->str:return hashlib.sha256(text.encode("utf-8")).hexdigest()
def _integrity(artifact:Mapping[str,Any],fp_key:str,id_key:str,prefix:str)->bool:
 body={k:v for k,v in artifact.items() if k not in {fp_key,id_key}}; rebuilt=canon(body,fp_key,id_key,prefix)
 return rebuilt.get(fp_key)==artifact.get(fp_key) and rebuilt.get(id_key)==artifact.get(id_key)
def _valid_branch(branch:str)->bool:return bool(BRANCH_RE.fullmatch(branch or "") and not branch.startswith(".") and "/." not in branch and not branch.endswith(".lock"))
def _valid_text(value:str,limit:int)->bool:return bool(value and len(value)<=limit and SAFE_TEXT.fullmatch(value))

def validate_push_closure(closure:Mapping[str,Any])->list[str]:
 errors=[]
 if closure.get("schema")!=PUSH_CLOSURE_SCHEMA:errors.append("invalid_push_closure_schema")
 if not _integrity(closure,"push_closure_fingerprint","push_closure_id","engineering-push-closure-"):errors.append("push_closure_fingerprint_invalid")
 if closure.get("sealed") is not True or closure.get("closure_status")!="closed" or closure.get("next_governed_action")!="push_complete":errors.append("push_closure_not_successful")
 if not closure.get("push_closure_id"):errors.append("missing_push_closure_id")
 if closure.get("pushed_commit_sha")!=closure.get("verified_remote_commit_sha") or not SHA_RE.fullmatch(str(closure.get("pushed_commit_sha") or "")):errors.append("push_closure_commit_invalid")
 for key in ("repository_id","remote_name","remote_url","source_branch"):
  if not closure.get(key):errors.append(f"push_closure_missing_{key}")
 return sorted(set(errors))

def build_pr_preparation(push_closure:Mapping[str,Any],*,repository_provider:str,repository_id:str,repository_owner:str,
 repository_name:str,remote_name:str,remote_url:str,source_branch:str,target_branch:str,target_commit_sha:str,title:str,body:str)->dict[str,Any]:
 errors=validate_push_closure(push_closure)
 if not re.fullmatch(r"[a-z][a-z0-9_-]{1,31}",repository_provider or ""):errors.append("invalid_repository_provider")
 if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}",repository_owner or "") or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}",repository_name or ""):errors.append("invalid_repository_coordinates")
 if repository_id!=push_closure.get("repository_id"):errors.append("repository_identity_mismatch")
 if remote_name!=push_closure.get("remote_name") or remote_url!=push_closure.get("remote_url"):errors.append("remote_identity_mismatch")
 if source_branch!=push_closure.get("source_branch"):errors.append("source_branch_mismatch")
 if not _valid_branch(source_branch) or not _valid_branch(target_branch):errors.append("invalid_branch")
 if source_branch==target_branch:errors.append("source_target_branch_equal")
 if not SHA_RE.fullmatch(target_commit_sha or ""):errors.append("invalid_target_commit")
 if not _valid_text(title,256):errors.append("invalid_title")
 if len(body)>10000 or not SAFE_TEXT.fullmatch(body):errors.append("invalid_body")
 payload={"schema":PREPARATION_SCHEMA,"push_closure_id":push_closure.get("push_closure_id"),"repository_provider":repository_provider,
  "repository_id":repository_id,"repository_owner":repository_owner,"repository_name":repository_name,"remote_name":remote_name,
  "remote_url":remote_url,"source_branch":source_branch,"target_branch":target_branch,"source_commit_sha":push_closure.get("pushed_commit_sha"),
  "target_commit_sha":target_commit_sha,"title":title,"body":body,"title_fingerprint":_sha(title),"body_fingerprint":_sha(body),
  "preparation_status":"prepared" if not errors else "blocked","reason_codes":sorted(set(errors)),"authority":NO_AUTHORITY}
 return canon(payload,"pull_request_preparation_fingerprint","pull_request_preparation_id","engineering-pr-preparation-")

def admit_repository_provider(preparation:Mapping[str,Any],adapter:RepositoryProviderAdapter)->dict[str,Any]:
 errors=[]
 if preparation.get("preparation_status")!="prepared":errors.append("preparation_not_ready")
 if adapter.provider_name!=preparation.get("repository_provider"):errors.append("provider_mismatch")
 observed=dict(adapter.inspect_repository(str(preparation.get("repository_owner")),str(preparation.get("repository_name"))))
 for key in ("repository_id","remote_url"):
  if observed.get(key)!=preparation.get(key):errors.append(f"{key}_mismatch")
 payload={"schema":ADMISSION_SCHEMA,"pull_request_preparation_reference":_ref(preparation),"push_closure_id":preparation.get("push_closure_id"),
  "repository_provider":adapter.provider_name,"repository_id":observed.get("repository_id"),"remote_url":observed.get("remote_url"),
  "admission_status":"admitted" if not errors else "blocked","reason_codes":sorted(set(errors)),"mutation_performed":False,"authority":NO_AUTHORITY}
 return canon(payload,"provider_admission_fingerprint","provider_admission_id","engineering-provider-admission-")

def verify_pr_remote(preparation:Mapping[str,Any],admission:Mapping[str,Any],adapter:RepositoryProviderAdapter)->dict[str,Any]:
 errors=[]
 if admission.get("admission_status")!="admitted" or admission.get("pull_request_preparation_reference")!=_ref(preparation):errors.append("provider_not_admitted")
 if admission.get("push_closure_id")!=preparation.get("push_closure_id"):errors.append("push_closure_id_mismatch")
 observed=dict(adapter.inspect_branches(preparation["repository_owner"],preparation["repository_name"],preparation["source_branch"],preparation["target_branch"],preparation["source_commit_sha"]))
 if not observed.get("source_exists"):errors.append("source_branch_missing")
 if not observed.get("target_exists"):errors.append("target_branch_missing")
 if observed.get("source_head")!=preparation.get("source_commit_sha"):errors.append("source_head_mismatch")
 if observed.get("target_head")!=preparation.get("target_commit_sha"):errors.append("target_head_mismatch")
 if not observed.get("source_commit_ancestor"):errors.append("source_commit_not_on_branch")
 if not observed.get("has_changes"):errors.append("no_changes")
 equivalent=adapter.find_equivalent_open_pull_request(preparation["repository_owner"],preparation["repository_name"],preparation["source_branch"],preparation["target_branch"])
 if equivalent:errors.append("equivalent_open_pull_request")
 payload={"schema":REMOTE_SCHEMA,"pull_request_preparation_reference":_ref(preparation),"provider_admission_reference":_ref(admission),
  "push_closure_id":preparation.get("push_closure_id"),"repository_id":preparation.get("repository_id"),"source_branch":preparation.get("source_branch"),
  "target_branch":preparation.get("target_branch"),"source_remote_head":observed.get("source_head"),"target_remote_head":observed.get("target_head"),
  "source_commit_sha":preparation.get("source_commit_sha"),"preparation_fingerprint":preparation.get("pull_request_preparation_fingerprint"),
  "equivalent_pull_request":equivalent,"verification_status":"verified" if not errors else "failed","reason_codes":sorted(set(errors)),"mutation_performed":False,"authority":NO_AUTHORITY}
 return canon(payload,"pr_remote_verification_fingerprint","pr_remote_verification_id","engineering-pr-remote-verification-")

def review_pull_request(preparation:Mapping[str,Any],remote:Mapping[str,Any],review:Mapping[str,Any])->dict[str,Any]:
 if not review.get("human_actor"):raise GovernedPullRequestError("missing_human_actor")
 if review.get("decision") not in {"approved","rejected","blocked"}:raise GovernedPullRequestError("invalid_review_decision")
 errors=[]
 if remote.get("verification_status")!="verified":errors.append("remote_not_verified")
 if remote.get("push_closure_id")!=preparation.get("push_closure_id"):errors.append("push_closure_id_mismatch")
 decision=review["decision"] if not errors else "blocked"
 payload={"schema":REVIEW_SCHEMA,"pull_request_preparation_reference":_ref(preparation),"remote_verification_reference":_ref(remote),
  "push_closure_id":preparation.get("push_closure_id"),"preparation_id":preparation.get("pull_request_preparation_id"),
  "preparation_fingerprint":preparation.get("pull_request_preparation_fingerprint"),"repository_id":preparation.get("repository_id"),
  "source_branch":preparation.get("source_branch"),"target_branch":preparation.get("target_branch"),"source_remote_head":remote.get("source_remote_head"),
  "target_remote_head":remote.get("target_remote_head"),"title_fingerprint":preparation.get("title_fingerprint"),"body_fingerprint":preparation.get("body_fingerprint"),
  "human_actor":review["human_actor"],"decision":decision,"reason_codes":errors,"authority":NO_AUTHORITY}
 return canon(payload,"pull_request_review_fingerprint","pull_request_review_id","engineering-pr-review-")

def authorize_pull_request(preparation:Mapping[str,Any],remote:Mapping[str,Any],review:Mapping[str,Any],authorization:Mapping[str,Any])->dict[str,Any]:
 if not authorization.get("human_actor"):raise GovernedPullRequestError("missing_authorization_actor")
 errors=[]
 if review.get("decision")!="approved":errors.append("review_not_approved")
 if review.get("pull_request_preparation_reference")!=_ref(preparation) or review.get("remote_verification_reference")!=_ref(remote):errors.append("stale_review")
 if any(x.get("push_closure_id")!=preparation.get("push_closure_id") for x in (remote,review)):errors.append("push_closure_id_mismatch")
 scope=authorization.get("scope") or {}
 expected={"provider":preparation.get("repository_provider"),"repository_id":preparation.get("repository_id"),"source_branch":preparation.get("source_branch"),"target_branch":preparation.get("target_branch"),"source_commit_sha":preparation.get("source_commit_sha"),"title_fingerprint":preparation.get("title_fingerprint"),"body_fingerprint":preparation.get("body_fingerprint"),"attempts":1}
 if scope!=expected:errors.append("authorization_scope_mismatch")
 authorized=authorization.get("decision")=="authorized" and not errors
 payload={"schema":AUTH_SCHEMA,"pull_request_preparation_reference":_ref(preparation),"remote_verification_reference":_ref(remote),
  "pull_request_review_reference":_ref(review),"push_closure_id":preparation.get("push_closure_id"),"human_actor":authorization["human_actor"],
  "decision":authorization.get("decision"),"authorized":authorized,"scope":scope,"usage_status":"unused","use_count":0,
  "reason_codes":sorted(set(errors)),"authority":PR_AUTHORITY if authorized else NO_AUTHORITY}
 return canon(payload,"pull_request_authorization_fingerprint","pull_request_authorization_id","engineering-pr-authorization-")

def build_pr_creation_request(preparation:Mapping[str,Any],remote:Mapping[str,Any],review:Mapping[str,Any],authorization:Mapping[str,Any])->dict[str,Any]:
 errors=[]
 if not authorization.get("authorized") or authorization.get("usage_status")!="unused":errors.append("authorization_not_available")
 if review.get("decision")!="approved":errors.append("review_not_approved")
 if any(x.get("push_closure_id")!=preparation.get("push_closure_id") for x in (remote,review,authorization)):errors.append("push_closure_id_mismatch")
 payload={"schema":REQUEST_SCHEMA,"pull_request_preparation_reference":_ref(preparation),"remote_verification_reference":_ref(remote),
  "pull_request_review_reference":_ref(review),"pull_request_authorization_reference":_ref(authorization),"push_closure_id":preparation.get("push_closure_id"),
  "repository_provider":preparation.get("repository_provider"),"repository_id":preparation.get("repository_id"),"repository_owner":preparation.get("repository_owner"),
  "repository_name":preparation.get("repository_name"),"source_branch":preparation.get("source_branch"),"target_branch":preparation.get("target_branch"),
  "source_commit_sha":preparation.get("source_commit_sha"),"title":preparation.get("title"),"body":preparation.get("body"),
  "request_status":"ready" if not errors else "blocked","reason_codes":sorted(set(errors)),"authority":NO_AUTHORITY}
 return canon(payload,"pull_request_creation_request_fingerprint","pull_request_creation_request_id","engineering-pr-request-")

def execute_pull_request(push_closure:Mapping[str,Any],preparation:Mapping[str,Any],admission:Mapping[str,Any],remote:Mapping[str,Any],review:Mapping[str,Any],authorization:Mapping[str,Any],request:Mapping[str,Any],adapter:RepositoryProviderAdapter)->tuple[dict[str,Any],dict[str,Any]]:
 errors=validate_push_closure(push_closure)
 if push_closure.get("push_closure_id")!=preparation.get("push_closure_id"):errors.append("push_closure_id_mismatch")
 if not _integrity(preparation,"pull_request_preparation_fingerprint","pull_request_preparation_id","engineering-pr-preparation-"):errors.append("preparation_integrity_invalid")
 if request.get("request_status")!="ready" or request.get("pull_request_preparation_reference")!=_ref(preparation):errors.append("request_not_ready")
 if review.get("decision")!="approved" or review.get("pull_request_preparation_reference")!=_ref(preparation):errors.append("review_not_approved")
 if not authorization.get("authorized") or authorization.get("usage_status")!="unused":errors.append("authorization_not_available")
 if authorization.get("pull_request_review_reference")!=_ref(review) or request.get("pull_request_authorization_reference")!=_ref(authorization):errors.append("authorization_reference_mismatch")
 if any(x.get("push_closure_id")!=preparation.get("push_closure_id") for x in (admission,remote,review,authorization,request)):errors.append("push_closure_id_mismatch")
 current=verify_pr_remote(preparation,admission,adapter)
 if current.get("verification_status")!="verified":errors.extend(current.get("reason_codes") or ["remote_freeze_failed"])
 if current.get("source_remote_head")!=remote.get("source_remote_head"):errors.append("source_branch_changed")
 if current.get("target_remote_head")!=remote.get("target_remote_head"):errors.append("target_branch_changed")
 if request.get("title")!=preparation.get("title") or request.get("body")!=preparation.get("body"):errors.append("title_body_substitution")
 if errors:raise GovernedPullRequestError(sorted(set(errors))[0])
 result=dict(adapter.create_pull_request({k:request[k] for k in ("repository_provider","repository_id","repository_owner","repository_name","source_branch","target_branch","source_commit_sha","title","body")}))
 status="created" if result.get("created") and result.get("provider_pr_id") else "failed"
 used={**authorization,"usage_status":"consumed","use_count":1}
 payload={"schema":EXECUTION_SCHEMA,"pull_request_creation_request_reference":_ref(request),"push_closure_id":preparation.get("push_closure_id"),
  "provider_pr_id":result.get("provider_pr_id"),"pr_number":result.get("pr_number"),"pr_url":result.get("pr_url"),"execution_status":status,
  "provider_status":result.get("status"),"attempt_count":1,"retry_performed":False,"authority":NO_AUTHORITY}
 return used,canon(payload,"pull_request_execution_fingerprint","pull_request_execution_id","engineering-pr-execution-")

def build_pr_evidence(preparation:Mapping[str,Any],review:Mapping[str,Any],authorization:Mapping[str,Any],execution:Mapping[str,Any],adapter:RepositoryProviderAdapter)->dict[str,Any]:
 observed=dict(adapter.inspect_pull_request(preparation["repository_owner"],preparation["repository_name"],str(execution.get("provider_pr_id"))))
 ok=execution.get("execution_status")=="created" and observed.get("provider_pr_id")==execution.get("provider_pr_id")
 payload={"schema":EVIDENCE_SCHEMA,"push_closure_id":preparation.get("push_closure_id"),"preparation_id":preparation.get("pull_request_preparation_id"),
  "review_id":review.get("pull_request_review_id"),"authorization_id":authorization.get("pull_request_authorization_id"),"execution_result_id":execution.get("pull_request_execution_id"),
  "provider":preparation.get("repository_provider"),"repository_id":preparation.get("repository_id"),"provider_pr_id":execution.get("provider_pr_id"),
  "pr_number":execution.get("pr_number"),"pr_url":execution.get("pr_url"),"source_branch":observed.get("source_branch"),"target_branch":observed.get("target_branch"),
  "source_commit_sha":observed.get("source_commit_sha"),"observed_source_remote_head":observed.get("source_head"),"observed_target_remote_head":observed.get("target_head"),
  "observed_pr_state":observed.get("state"),"evidence_status":"complete" if ok else "failed","authority":NO_AUTHORITY}
 return canon(payload,"pull_request_evidence_fingerprint","pull_request_evidence_id","engineering-pr-evidence-")

def verify_created_pull_request(preparation:Mapping[str,Any],execution:Mapping[str,Any],evidence:Mapping[str,Any],adapter:RepositoryProviderAdapter)->dict[str,Any]:
 observed=dict(adapter.inspect_pull_request(preparation["repository_owner"],preparation["repository_name"],str(execution.get("provider_pr_id"))));errors=[]
 if evidence.get("evidence_status")!="complete":errors.append("evidence_incomplete")
 if observed.get("repository_id")!=preparation.get("repository_id"):errors.append("repository_identity_mismatch")
 if observed.get("source_branch")!=preparation.get("source_branch") or observed.get("target_branch")!=preparation.get("target_branch"):errors.append("branch_mismatch")
 if observed.get("source_commit_sha")!=preparation.get("source_commit_sha") or observed.get("source_head")!=preparation.get("source_commit_sha"):errors.append("source_commit_mismatch")
 if observed.get("state")!="open" or observed.get("merged") or observed.get("closed"):errors.append("pr_not_awaiting_review")
 payload={"schema":POST_SCHEMA,"push_closure_id":preparation.get("push_closure_id"),"pull_request_evidence_reference":_ref(evidence),
  "provider_pr_id":execution.get("provider_pr_id"),"repository_id":observed.get("repository_id"),"source_branch":observed.get("source_branch"),
  "target_branch":observed.get("target_branch"),"source_commit_sha":observed.get("source_commit_sha"),"observed_state":observed.get("state"),
  "merged":bool(observed.get("merged")),"closed":bool(observed.get("closed")),"unauthorized_mutation_performed":False,
  "verification_status":"verified" if not errors else "failed","reason_codes":sorted(set(errors)),"authority":NO_AUTHORITY}
 return canon(payload,"pull_request_post_verification_fingerprint","pull_request_post_verification_id","engineering-pr-post-verification-")

def close_pull_request(preparation:Mapping[str,Any],remote:Mapping[str,Any],review:Mapping[str,Any],authorization:Mapping[str,Any],execution:Mapping[str,Any],evidence:Mapping[str,Any],post:Mapping[str,Any])->dict[str,Any]:
 errors=[];cid=preparation.get("push_closure_id")
 if any(x.get("push_closure_id")!=cid for x in (remote,review,authorization,execution,evidence,post)):errors.append("push_closure_id_mismatch")
 if authorization.get("usage_status")!="consumed" or authorization.get("use_count")!=1:errors.append("authorization_not_consumed_once")
 if post.get("verification_status")!="verified":errors.append("post_verification_failed")
 payload={"schema":CLOSURE_SCHEMA,"push_closure_id":cid,"preparation_id":preparation.get("pull_request_preparation_id"),
  "remote_verification_id":remote.get("pr_remote_verification_id"),"review_id":review.get("pull_request_review_id"),
  "authorization_id":authorization.get("pull_request_authorization_id"),"execution_result_id":execution.get("pull_request_execution_id"),
  "evidence_id":evidence.get("pull_request_evidence_id"),"post_verification_id":post.get("pull_request_post_verification_id"),
  "provider_pr_id":execution.get("provider_pr_id"),"repository_id":preparation.get("repository_id"),"source_branch":preparation.get("source_branch"),
  "target_branch":preparation.get("target_branch"),"source_commit_sha":preparation.get("source_commit_sha"),"sealed":not errors,
  "closure_status":"awaiting_merge_review" if not errors else "failed","reason_codes":sorted(set(errors)),"merge_authorized":False,"merged":False,"authority":NO_AUTHORITY}
 return canon(payload,"pull_request_closure_fingerprint","pull_request_closure_id","engineering-pr-closure-")

def inspect_pr_state(bundle:Mapping[str,Any])->dict[str,Any]:
 g=lambda k:bundle.get(STORE_FILES[k]) or {}; return {"schema":"zero.engineering.pull_request_state.v1","preparation_status":g("preparation").get("preparation_status","not_started"),"provider_admission_status":g("admission").get("admission_status","not_started"),"remote_verification_status":g("remote").get("verification_status","not_started"),"review_status":g("review").get("decision","not_started"),"authorization_status":"authorized" if g("authorization").get("authorized") else "not_authorized","execution_status":g("execution").get("execution_status","not_started"),"post_verification_status":g("post").get("verification_status","not_started"),"closure_status":g("closure").get("closure_status","not_started"),**{f"will_{x}":False for x in ("create_pr","retry","merge","push","delete_branch","tag","release","workflow")}}
