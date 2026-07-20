from __future__ import annotations
from copy import deepcopy
from typing import Any, Mapping
from core.engineering.engineering_mutation_transaction_common import canonical_json, fingerprint

SESSION_SCHEMA = SCHEMA = "zero.engineering.execution_session.v1"
REPORT_SCHEMA = "zero.engineering.execution_session_report.v1"
AUTHORITY_BOUNDARY = {"approval":"not_granted","authorization":"not_granted","token":"not_granted","mutation":"not_granted","shell":"not_granted","git":"not_granted","network":"not_granted"}
EMPTY = None
STAGES = ("awaiting_approval","approved","authorized","prepared","ready_for_execution","awaiting_verification","verified","completed","closed")
TERMINAL = {"closed","failed","invalid"}
DENY_KEYS = {"command","shell_command","git_command","network_request","socket_request","url","token_secret","approval_secret","authorization_secret","mutation_payload","file_content","patch","diff","source_content","replacement_content","executable","approval_granted","authorization_granted","token_issued","mutation_authorized"}
REFS = {
 "proposal":("proposal_identity","proposal_fingerprint"),"proposal_linkage":("proposal_linkage_identity","proposal_linkage_fingerprint"),"approval":("approval_identity","approval_fingerprint"),"authorization":("authorization_identity","authorization_fingerprint"),"authorized_scope":("authorized_scope_identity","authorized_scope_fingerprint"),"preparation":("preparation_identity","preparation_fingerprint"),"token":("token_identity","token_fingerprint"),"execution":("execution_identity","execution_fingerprint"),"verification_result":("verification_result_identity","verification_result_fingerprint"),"completion":("completion_identity","completion_fingerprint"),"closure":("closure_identity","closure_fingerprint")}

def _fp_body(a: Mapping[str, Any]) -> str: return fingerprint({k:v for k,v in a.items() if k!="fingerprint"})
def _ident(a: Mapping[str, Any], *names: str) -> Any:
    for n in names:
        if a.get(n): return a.get(n)
    return a.get("artifact_identity")
def _afp(a: Mapping[str, Any]) -> Any: return a.get("fingerprint") or a.get("artifact_fingerprint")
def _contains_denied(v: Any) -> bool:
    if isinstance(v, Mapping): return any(str(k).lower() in DENY_KEYS or _contains_denied(x) for k,x in v.items())
    if isinstance(v, list): return any(_contains_denied(x) for x in v)
    return False

def derive_current_stage(session: Mapping[str, Any]) -> str:
    if session.get("closure_identity"): return "closed"
    if session.get("completion_identity"): return "completed"
    if session.get("verification_result_identity"): return "verified"
    if session.get("execution_identity"): return "awaiting_verification"
    if session.get("token_identity"): return "ready_for_execution"
    if session.get("preparation_identity"): return "prepared"
    if session.get("authorization_identity"): return "authorized"
    if session.get("approval_identity"): return "approved"
    return "awaiting_approval"

def _status_for(stage: str) -> str: return stage

def _history_for(session: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows=[]
    schema_by={"proposal":"zero.engineering.change_proposal.v1","proposal_linkage":"zero.engineering.proposal_linkage.v1","approval":"zero.engineering.approval_decision.v1","authorization":"zero.engineering.authorization_decision.v1","authorized_scope":"zero.engineering.mutation_authorized_scope.v1","preparation":"zero.engineering.mutation_preparation_closure.v1","token":"zero.engineering.mutation_preparation_token.v1","execution":"zero.engineering.workspace_mutation_result.v1","verification_result":"zero.engineering.verification_result.v1","completion":"zero.engineering.completion.v1","closure":"zero.engineering.task_closure.v1"}
    stage_by={"proposal":"awaiting_approval","approval":"approved","authorization":"authorized","authorized_scope":"authorized","preparation":"prepared","token":"ready_for_execution","execution":"awaiting_verification","verification_result":"verified","completion":"completed","closure":"closed"}
    for name in ("proposal","approval","authorization","authorized_scope","preparation","token","execution","verification_result","completion","closure"):
        ik,fk=REFS[name]
        if session.get(ik): rows.append({"stage":stage_by[name],"artifact_schema":schema_by[name],"artifact_identity":session.get(ik),"artifact_fingerprint":session.get(fk),"transition_reason":"accepted_"+name})
    return rows

def seal_session(body: Mapping[str, Any]) -> dict[str, Any]:
    s=deepcopy(dict(body)); stage=derive_current_stage(s); s["current_stage"]=stage; s["session_status"]=_status_for(stage); s["stage_history"]=_history_for(s); s.setdefault("replay_count",0); s.setdefault("resume_count",0); s.setdefault("blocked_reason_codes",[]); s.setdefault("failure_reason_codes",[]); s.setdefault("bounded_summary",{}); s["deterministic"]=True; s["immutable"]=True; s["authority_boundary"]=dict(AUTHORITY_BOUNDARY); s["schema"]=SESSION_SCHEMA
    s["fingerprint"]=_fp_body(s); return s

def create_engineering_execution_session(*, task: Mapping[str, Any], proposal: Mapping[str, Any], proposal_linkage: Mapping[str, Any]) -> dict[str, Any]:
    task_id=str(task.get("task_id") or task.get("task_identity") or proposal_linkage.get("task_id") or "")
    repo=task.get("repository_identity") or proposal.get("repository_identity") or proposal_linkage.get("repository_identity")
    body={"execution_session_id":"engineering-execution-session-"+fingerprint({"task_id":task_id,"repository_identity":repo,"proposal_identity":_ident(proposal,"proposal_id"),"proposal_fingerprint":_afp(proposal),"proposal_linkage_identity":_ident(proposal_linkage,"proposal_linkage_id"),"proposal_linkage_fingerprint":_afp(proposal_linkage)})[:24],"task_id":task_id,"repository_identity":repo,"proposal_identity":_ident(proposal,"proposal_id"),"proposal_fingerprint":_afp(proposal),"proposal_linkage_identity":_ident(proposal_linkage,"proposal_linkage_id"),"proposal_linkage_fingerprint":_afp(proposal_linkage)}
    for ik,fk in REFS.values(): body.setdefault(ik, EMPTY); body.setdefault(fk, EMPTY)
    body["proposal_identity"]=_ident(proposal,"proposal_id"); body["proposal_fingerprint"]=_afp(proposal); body["proposal_linkage_identity"]=_ident(proposal_linkage,"proposal_linkage_id"); body["proposal_linkage_fingerprint"]=_afp(proposal_linkage)
    return seal_session(body)

def validate_engineering_execution_session(v: Any) -> Any:
    errors=[]
    if not isinstance(v, Mapping):
        return {"valid":False,"errors":["artifact_not_mapping"]}
    if v.get("schema")!=SESSION_SCHEMA: errors.append("schema_mismatch")
    if not str(v.get("execution_session_id","")).startswith("engineering-execution-session-"): errors.append("identity_mismatch")
    if v.get("deterministic") is not True or v.get("immutable") is not True: errors.append("mutable_or_nondeterministic")
    if v.get("authority_boundary")!=AUTHORITY_BOUNDARY: errors.append("authority_boundary_invalid")
    if _contains_denied(v): errors.append("executable_or_authority_payload_denied")
    if v.get("current_stage")!=derive_current_stage(v): errors.append("current_stage_not_derived")
    if v.get("stage_history")!=_history_for(v): errors.append("stage_history_invalid")
    if not isinstance(v.get("replay_count"), int) or v.get("replay_count")<0 or v.get("replay_count")>1000: errors.append("replay_count_invalid")
    if not isinstance(v.get("resume_count"), int) or v.get("resume_count")<0 or v.get("resume_count")>1000: errors.append("resume_count_invalid")
    if v.get("fingerprint")!=_fp_body(v): errors.append("fingerprint_mismatch")
    return {"valid":not errors,"errors":errors}

def build_engineering_execution_session(*args, **kwargs):
    if args and len(args)==2 and not kwargs:
        admission,intake=args
        task={"task_id": intake.get("task_id", "legacy"), "repository_identity": intake.get("repository_identity")}
        proposal={"proposal_id": intake.get("proposal_identity", "legacy-proposal"), "fingerprint": intake.get("proposal_fingerprint", "0"*64), "repository_identity": intake.get("repository_identity")}
        linkage={"proposal_linkage_id": intake.get("proposal_linkage_identity", "legacy-linkage"), "fingerprint": intake.get("proposal_linkage_fingerprint", "0"*64), "task_id": task["task_id"], "repository_identity": task.get("repository_identity")}
        out=create_engineering_execution_session(task=task, proposal=proposal, proposal_linkage=linkage)
        out["session_authority"]={"non_reusable": True, "mutation_authority": "not_granted"}
        return out
    return create_engineering_execution_session(**kwargs)
build_execution_session = build_engineering_execution_session
__all__=["SESSION_SCHEMA","REPORT_SCHEMA","AUTHORITY_BOUNDARY","create_engineering_execution_session","build_engineering_execution_session","build_execution_session","derive_current_stage","seal_session","validate_engineering_execution_session","REFS"]
