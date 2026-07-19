
from __future__ import annotations
import argparse, hashlib, json, sys
from typing import Any, Mapping, Sequence

SCHEMAS = {
 "mutation_authorization_policy":"zero.engineering.mutation_authorization_policy.v1",
 "mutation_authorization_request":"zero.engineering.mutation_authorization_request.v1",
 "mutation_authorization_eligibility":"zero.engineering.mutation_authorization_eligibility.v1",
 "mutation_authorization_decision":"zero.engineering.mutation_authorization_decision.v1",
 "mutation_authorized_scope":"zero.engineering.mutation_authorized_scope.v1",
 "mutation_authorization_verification":"zero.engineering.mutation_authorization_verification.v1",
 "mutation_authorization_token_eligibility":"zero.engineering.mutation_authorization_token_eligibility.v1",
 "mutation_authorization_token":"zero.engineering.mutation_authorization_token.v1",
 "mutation_transaction_policy":"zero.engineering.mutation_transaction_policy.v1",
 "mutation_transaction_admission":"zero.engineering.mutation_transaction_admission.v1",
 "mutation_transaction_plan":"zero.engineering.mutation_transaction_plan.v1",
 "mutation_atomicity_plan":"zero.engineering.mutation_atomicity_plan.v1",
 "mutation_backup_plan":"zero.engineering.mutation_backup_plan.v1",
 "mutation_rollback_plan":"zero.engineering.mutation_rollback_plan.v1",
 "mutation_commit_boundary":"zero.engineering.mutation_commit_boundary.v1",
 "mutation_recovery_plan":"zero.engineering.mutation_recovery_plan.v1",
 "mutation_transaction_package":"zero.engineering.mutation_transaction_package.v1",
 "mutation_transaction_package_validation":"zero.engineering.mutation_transaction_package_validation.v1",
 "mutation_transaction_readiness":"zero.engineering.mutation_transaction_readiness.v1",
 "mutation_executor_handoff":"zero.engineering.mutation_executor_handoff.v1",
 "mutation_transaction_evidence":"zero.engineering.mutation_transaction_evidence.v1",
 "mutation_transaction_closure":"zero.engineering.mutation_transaction_closure.v1",
}
FALSE_FLAGS=("mutation_executor_invoked","mutation_performed","filesystem_write_performed","patch_applied","git_invoked","shell_invoked","runtime_kernel_invoked","token_consumed","transaction_started","commit_started","commit_completed","rollback_performed","recovery_performed","backup_created","authorization_token_consumed","preparation_token_consumed")
TOKEN_PURPOSE="workspace_mutation_transaction_admission"
PREP_TOKEN_PURPOSE="workspace_mutation_preparation_handoff"

def canonical_json(v:Any)->str: return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def fingerprint(v:Any)->str: return hashlib.sha256(canonical_json(v).encode()).hexdigest()
def identity(prefix:str, body:Mapping[str,Any])->str: return prefix+"-"+fingerprint(body)[:24]
def reasons(xs:Sequence[str])->list[str]: return sorted(set(str(x) for x in xs if x))
def seq(v:Any)->list[Any]: return list(v) if isinstance(v,(list,tuple)) else []
def mapping(v:Any)->dict[str,Any]: return dict(v) if isinstance(v,dict) else {}
def ref(a:Mapping[str,Any], id_key:str|None=None)->dict[str,Any]:
    k=id_key or next((x for x in a if x.endswith("_id") or x=="token_id" or x=="handoff_id"), "id")
    return {"id":a.get(k),"fingerprint":a.get("fingerprint"),"schema":a.get("schema")}
def finish(prefix:str, schema_key:str, id_key:str, body:dict[str,Any])->dict[str,Any]:
    b=dict(body); b["schema"]=SCHEMAS[schema_key]; b[id_key]=identity(prefix,{k:v for k,v in b.items() if k not in (id_key,"fingerprint")}); b["fingerprint"]=fingerprint({k:v for k,v in b.items() if k!="fingerprint"}); return b
def false_invariants(*arts:Mapping[str,Any])->list[str]: return reasons([k+"_not_false" for a in arts for k in FALSE_FLAGS if k in a and a.get(k) is not False])
def ops_from_package(pkg): return seq(pkg.get("operations") or pkg.get("prepared_operations") or pkg.get("ordered_operations"))
def op_id(o): return o.get("operation_id")
def op_fp(o): return o.get("operation_fingerprint") or o.get("fingerprint") or fingerprint(o)
def op_type(o): return o.get("operation_type") or o.get("operation_class")
def target_fp(o): return o.get("target_path_fingerprint") or o.get("target_relative_path_fingerprint") or o.get("path_fingerprint")
def content_fp(o): return o.get("content_fingerprint") or o.get("proposed_content_fingerprint")
def diff_fp(o): return o.get("diff_fingerprint")
def pre_fp(o): return o.get("precondition_fingerprint")
def op_summary(o):
    return {"operation_id":op_id(o),"operation_fingerprint":op_fp(o),"operation_type":op_type(o),"target_path_fingerprint":target_fp(o),"content_fingerprint":content_fp(o),"diff_fingerprint":diff_fp(o),"precondition_fingerprint":pre_fp(o),"expected_before_fingerprint":o.get("expected_before_fingerprint"),"expected_after_fingerprint":o.get("expected_after_fingerprint") or o.get("proposed_after_fingerprint"),"content_byte_count":int(o.get("content_byte_count") or 0),"diff_entry_count":int(o.get("diff_entry_count") or 0)}
def summaries(pkg): return [op_summary(o) for o in ops_from_package(pkg)]
def byid(s): return {x["operation_id"]:x for x in s if x.get("operation_id")}
def subset_ids(child,parent): return set(child).issubset(set(parent)) and len(child)==len(set(child))
def scope_narrows(child,parent): return set(seq(child)).issubset(set(seq(parent)))
def authority_narrows(child,parent): return set(seq(child)).issubset(set(seq(parent)))
def counts(s): return {"operation_count":len(s),"file_count":len({x.get("target_path_fingerprint") for x in s if x.get("target_path_fingerprint")}),"content_byte_total":sum(x.get("content_byte_count",0) for x in s),"diff_entry_total":sum(x.get("diff_entry_count",0) for x in s)}
def conflicts(s):
    t=[x.get("target_path_fingerprint") for x in s if x.get("target_path_fingerprint")]
    return ["duplicate_target_conflict"] if len(t)!=len(set(t)) else []
def prohibited(v:Any)->list[str]:
    bad=[]
    banned=("proposed_content","content","raw_diff","absolute_path","credential","password","private_key","api_key","bearer","authorization_header","session_cookie","traceback","stdout","stderr","log")
    def walk(x):
        if callable(x): bad.append("callable_payload")
        elif isinstance(x,dict):
            for k,val in x.items():
                lk=str(k).lower()
                if any(b in lk for b in banned): bad.append("prohibited_"+lk)
                walk(val)
        elif isinstance(x,(list,tuple)):
            for y in x: walk(y)
    walk(v); return reasons(bad)
def valid_upstream(handoff, closure, readiness, token, token_elig, pkg, validation, approval_verification, decision, approved_scope):
    rs=[]
    checks=[(handoff,"zero.engineering.mutation_handoff.v1","handed_off"),(closure,"zero.engineering.mutation_preparation_closure.v1","closed"),(readiness,"zero.engineering.mutation_readiness_verification.v1","ready"),(token,"zero.engineering.mutation_preparation_token.v1","issued"),(token_elig,"zero.engineering.mutation_preparation_token_eligibility.v1","eligible"),(pkg,"zero.engineering.mutation_package.v1","packaged"),(validation,"zero.engineering.mutation_package_validation.v1","valid"),(approval_verification,"zero.engineering.operator_approval_verification.v1","verified"),(decision,"zero.engineering.operator_approval_decision.v1","approved"),(approved_scope,"zero.engineering.operator_approved_scope.v1","sealed")]
    for a,sch,st in checks:
        if a.get("schema")!=sch: rs.append(sch.split('.')[-2]+"_schema_invalid")
        if a.get("status")!=st: rs.append(sch.split('.')[-2]+"_status_invalid")
    if token.get("token_consumed") is not False or token.get("use_limit")!=1: rs.append("preparation_token_invalid")
    if handoff.get("operator_approval_obtained") is not True or handoff.get("preparation_completed") is not True: rs.append("handoff_not_ready")
    rs += false_invariants(handoff, closure, readiness, token, pkg, validation)
    ids=[pkg.get("mutation_package_id"), handoff.get("mutation_package_id"), validation.get("mutation_package_id"), token.get("mutation_package_id")]
    if len(set([x for x in ids if x]))>1: rs.append("mutation_package_linkage_mismatch")
    return reasons(rs)

def build_mutation_authorization_policy(p=None):
    p=mapping(p); rs=[]
    body={"status":"active","allowed_operator_identity_classes":seq(p.get("allowed_operator_identity_classes")) or ["human_operator"],"allowed_mutation_operation_classes":seq(p.get("allowed_mutation_operation_classes")) or ["create_text_file","replace_text_file","delete_file","rename_path"],"maximum_authorized_operations":p.get("maximum_authorized_operations",100),"maximum_authorized_files":p.get("maximum_authorized_files",100),"maximum_authorized_content_bytes":p.get("maximum_authorized_content_bytes",1000000),"maximum_authorized_diff_entries":p.get("maximum_authorized_diff_entries",10000),"allowed_path_prefixes":seq(p.get("allowed_path_prefixes")),"allowed_authority_constraints":seq(p.get("allowed_authority_constraints")),"allowed_workspace_ids":seq(p.get("allowed_workspace_ids")),"authorization_mode":p.get("authorization_mode","explicit_human"),"partial_authorization_allowed":bool(p.get("partial_authorization_allowed",False)),"operator_reason_required":bool(p.get("operator_reason_required",True)),"require_prior_operator_approval":True,"require_preparation_token":True,"authorization_token_use_limit":1,"self_authorization_allowed":False,"automated_authorization_allowed":False,"delegated_authorization_allowed":False,"multi_party_authorization_required":False,"git_allowed":False,"shell_allowed":False,"external_tools_allowed":False,"symlink_operations_allowed":False,"binary_operations_allowed":False}
    for k in ("maximum_authorized_operations","maximum_authorized_files","maximum_authorized_content_bytes","maximum_authorized_diff_entries"):
        if type(body[k]) is not int or body[k] < 0: rs.append(k+"_invalid")
    if p.get("automated_authorization_allowed") is True: rs.append("automated_authorization_rejected")
    if p.get("self_authorization_allowed") is True: rs.append("self_authorization_rejected")
    body["status"]="invalid" if rs else p.get("status","active"); body["reason_codes"]=reasons(rs); return finish("mutauth-policy","mutation_authorization_policy","policy_id",body)

def build_mutation_authorization_request(handoff, closure, readiness, token, token_elig, pkg, validation, approval_verification, approved_scope, request=None):
    request=mapping(request); s=summaries(pkg); ids=request.get("requested_operation_ids") or [x["operation_id"] for x in s]
    chosen=[byid(s)[i] for i in ids if i in byid(s)]; rs=[]
    if len(chosen)!=len(ids): rs.append("requested_operation_expansion")
    rs += valid_upstream(handoff,closure,readiness,token,token_elig,pkg,validation,approval_verification,{"schema":"zero.engineering.operator_approval_decision.v1","status":"approved"},approved_scope)
    body={"status":"invalid" if rs else "requested","mutation_handoff_id":handoff.get("handoff_id") or handoff.get("mutation_handoff_id"),"mutation_handoff_fingerprint":handoff.get("fingerprint"),"preparation_closure_id":closure.get("closure_id"),"preparation_closure_fingerprint":closure.get("fingerprint"),"mutation_package_id":pkg.get("mutation_package_id"),"mutation_package_fingerprint":pkg.get("fingerprint"),"package_validation_id":validation.get("validation_id"),"package_validation_fingerprint":validation.get("fingerprint"),"preparation_token_id":token.get("token_id"),"preparation_token_fingerprint":token.get("fingerprint"),"operator_approval_verification_id":approval_verification.get("verification_id"),"requested_operations":chosen,"requested_operation_ids":[x["operation_id"] for x in chosen],"requested_operation_fingerprints":[x["operation_fingerprint"] for x in chosen],"requested_target_path_fingerprints":[x.get("target_path_fingerprint") for x in chosen],"requested_content_fingerprints":[x.get("content_fingerprint") for x in chosen],"requested_diff_fingerprints":[x.get("diff_fingerprint") for x in chosen],"requested_precondition_fingerprints":[x.get("precondition_fingerprint") for x in chosen],"requested_workspace_id":pkg.get("workspace_id") or handoff.get("workspace_id"),"requested_workspace_root_fingerprint":pkg.get("workspace_root_fingerprint") or handoff.get("workspace_root_fingerprint"),"requested_scope":seq(request.get("requested_scope") or approved_scope.get("scope_constraints")),"requested_authority_constraints":seq(request.get("requested_authority_constraints") or approved_scope.get("authority_constraints")),"request_reason_code":request.get("request_reason_code","operator_requested_mutation_authorization"),"human_authorization_required":True,"automated_authorization_allowed":False,"mutation_authorized":False,"transaction_started":False,"mutation_performed":False,"reason_codes":reasons(rs)}; return finish("mutauth-request","mutation_authorization_request","request_id",body)

def evaluate_mutation_authorization_eligibility(policy,request,handoff,closure,readiness,token,token_elig,pkg,validation,approval_verification,approved_scope):
    rs=[]; s=request.get("requested_operations",[]); c=counts(s)
    if policy.get("status")!="active": rs.append("policy_not_active")
    if request.get("status")!="requested": rs.append("request_not_requested")
    rs += valid_upstream(handoff,closure,readiness,token,token_elig,pkg,validation,approval_verification,{"schema":"zero.engineering.operator_approval_decision.v1","status":"approved"},approved_scope)
    if c["operation_count"]>policy.get("maximum_authorized_operations",0): rs.append("operation_bound_exceeded")
    if c["file_count"]>policy.get("maximum_authorized_files",0): rs.append("file_bound_exceeded")
    if c["content_byte_total"]>policy.get("maximum_authorized_content_bytes",0): rs.append("content_bound_exceeded")
    if c["diff_entry_total"]>policy.get("maximum_authorized_diff_entries",0): rs.append("diff_bound_exceeded")
    if request.get("automated_authorization_allowed") is not False: rs.append("automated_authorization_not_false")
    rs += conflicts(s); status="eligible" if not rs else "not_eligible"; return finish("mutauth-elig","mutation_authorization_eligibility","eligibility_id",{"status":status,"policy_id":policy.get("policy_id"),"request_id":request.get("request_id"),"eligible_operation_ids":request.get("requested_operation_ids",[]),"workspace_id":request.get("requested_workspace_id"),"reason_codes":reasons(rs)})

def build_mutation_authorization_decision(d,policy,request,eligibility,pkg):
    d=mapping(d); rs=[]; dec=d.get("decision"); aid=d.get("authorizer_id"); cls=d.get("authorizer_identity_class"); req_ids=request.get("requested_operation_ids",[]); auth_ids=seq(d.get("authorized_operation_ids"))
    if not aid or not isinstance(aid,str) or not aid.strip(): rs.append("authorizer_id_invalid")
    if cls not in seq(policy.get("allowed_operator_identity_classes")): rs.append("authorizer_identity_class_not_allowed")
    if dec not in ("authorized","partially_authorized","rejected"): rs.append("authorization_decision_invalid")
    if d.get("automated_authorization") is True: rs.append("automated_authorization_rejected")
    if dec=="authorized" and auth_ids!=req_ids: rs.append("authorized_requires_all_requested")
    if dec=="partially_authorized" and not policy.get("partial_authorization_allowed"): rs.append("partial_authorization_not_allowed")
    if dec=="rejected" and auth_ids: rs.append("rejected_authorizes_operations")
    if not subset_ids(auth_ids, req_ids): rs.append("authorized_operation_not_subset")
    bm=byid(request.get("requested_operations",[])); chosen=[bm[i] for i in auth_ids if i in bm]
    if len(chosen)!=len(auth_ids): rs.append("operation_substitution")
    body={"status":"invalid" if rs else dec,"authorizer_id":aid,"authorizer_identity_class":cls,"authorizer_identity_fingerprint":fingerprint({"authorizer_id":aid,"authorizer_identity_class":cls}) if aid and cls else None,"decision":dec,"decision_reason_code":d.get("decision_reason_code"),"reviewed_mutation_handoff_id":request.get("mutation_handoff_id"),"reviewed_mutation_handoff_fingerprint":request.get("mutation_handoff_fingerprint"),"reviewed_mutation_package_id":pkg.get("mutation_package_id"),"reviewed_mutation_package_fingerprint":pkg.get("fingerprint"),"reviewed_operation_ids":req_ids,"authorized_operations":[] if dec=="rejected" else chosen,"authorized_operation_ids":[] if dec=="rejected" else auth_ids,"authorized_target_path_fingerprints":[x.get("target_path_fingerprint") for x in ([] if dec=="rejected" else chosen)],"authorized_content_fingerprints":[x.get("content_fingerprint") for x in ([] if dec=="rejected" else chosen)],"authorized_diff_fingerprints":[x.get("diff_fingerprint") for x in ([] if dec=="rejected" else chosen)],"authorized_precondition_fingerprints":[x.get("precondition_fingerprint") for x in ([] if dec=="rejected" else chosen)],"authorized_workspace_id":request.get("requested_workspace_id"),"authorized_workspace_root_fingerprint":request.get("requested_workspace_root_fingerprint"),"authorized_scope":seq(d.get("authorized_scope") or request.get("requested_scope")),"authorized_authority_constraints":seq(d.get("authorized_authority_constraints") or request.get("requested_authority_constraints")),"decision_sequence":d.get("decision_sequence",0),"decision_nonce":d.get("decision_nonce"),"human_authorization_decision":False if rs else True,"automated_authorization":False,"mutation_authorized":False if rs or dec=="rejected" else True,"transaction_started":False,"mutation_performed":False,"reason_codes":reasons(rs)}; return finish("mutauth-decision","mutation_authorization_decision","decision_id",body)

def seal_mutation_authorized_scope(decision,request,pkg):
    rs=[]
    if decision.get("status")=="invalid": rs.append("decision_invalid")
    ops=decision.get("authorized_operations",[]); c=counts(ops); status="empty" if decision.get("status")=="rejected" else ("invalid" if rs else "sealed")
    body={"status":status,"authorized_operations":ops,"authorized_operation_ids":[x.get("operation_id") for x in ops],"authorized_operation_fingerprints":[x.get("operation_fingerprint") for x in ops],"authorized_target_path_fingerprints":[x.get("target_path_fingerprint") for x in ops],"authorized_content_fingerprints":[x.get("content_fingerprint") for x in ops],"authorized_diff_fingerprints":[x.get("diff_fingerprint") for x in ops],"authorized_precondition_fingerprints":[x.get("precondition_fingerprint") for x in ops],"authorized_operation_classes":[x.get("operation_type") for x in ops],"authorized_path_prefixes":decision.get("authorized_scope",[]),"authorized_authority_constraints":decision.get("authorized_authority_constraints",[]),"workspace_id":decision.get("authorized_workspace_id"),"workspace_root_fingerprint":decision.get("authorized_workspace_root_fingerprint"),**c,"mutation_package_id":pkg.get("mutation_package_id"),"mutation_package_fingerprint":pkg.get("fingerprint"),"authorization_decision_id":decision.get("decision_id"),"authorization_decision_fingerprint":decision.get("fingerprint"),"reason_codes":reasons(rs)}; return finish("mutauth-scope","mutation_authorized_scope","authorized_scope_id",body)

def verify_mutation_authorization(policy,request,eligibility,decision,scope,pkg):
    rs=[]
    if policy.get("status")!="active": rs.append("policy_invalid")
    if request.get("status")!="requested": rs.append("request_invalid")
    if eligibility.get("status")!="eligible": rs.append("eligibility_invalid")
    if decision.get("status") not in ("authorized","partially_authorized","rejected"): rs.append("decision_invalid")
    if scope.get("status") not in ("sealed","empty"): rs.append("scope_invalid")
    if decision.get("automated_authorization") is not False or decision.get("human_authorization_decision") is not True: rs.append("human_authorization_invalid")
    if not scope_narrows(decision.get("authorized_scope",[]),request.get("requested_scope",[])): rs.append("scope_expansion")
    if not authority_narrows(decision.get("authorized_authority_constraints",[]),request.get("requested_authority_constraints",[])): rs.append("authority_expansion")
    if decision.get("authorized_workspace_id")!=request.get("requested_workspace_id"): rs.append("workspace_identity_mismatch")
    rs += false_invariants(request,decision)
    body={"status":"verified" if not rs else "not_verified","policy_id":policy.get("policy_id"),"request_id":request.get("request_id"),"eligibility_id":eligibility.get("eligibility_id"),"authorization_decision_id":decision.get("decision_id"),"authorization_decision_fingerprint":decision.get("fingerprint"),"authorized_scope_id":scope.get("authorized_scope_id"),"authorized_scope_fingerprint":scope.get("fingerprint"),"workspace_id":request.get("requested_workspace_id"),"workspace_root_fingerprint":request.get("requested_workspace_root_fingerprint"),"mutation_authorized":decision.get("mutation_authorized") is True,"transaction_started":False,"mutation_performed":False,"reason_codes":reasons(rs)}; return finish("mutauth-ver","mutation_authorization_verification","verification_id",body)

def evaluate_mutation_authorization_token_eligibility(verification,decision,scope,pkg,prep_token,consumed_token_record=None):
    rs=[]
    if verification.get("status")!="verified": rs.append("authorization_not_verified")
    if decision.get("status") not in ("authorized","partially_authorized"): rs.append("decision_not_authorized")
    if scope.get("status")!="sealed" or not scope.get("authorized_operation_ids"): rs.append("authorized_scope_empty")
    if prep_token.get("token_consumed") is not False or prep_token.get("use_limit")!=1: rs.append("preparation_token_invalid")
    if mapping(consumed_token_record).get("token_consumed") is True: rs.append("authorization_token_already_consumed")
    body={"status":"eligible" if not rs else "not_eligible","authorization_verification_id":verification.get("verification_id"),"authorization_decision_id":decision.get("decision_id"),"authorized_scope_id":scope.get("authorized_scope_id"),"mutation_package_id":pkg.get("mutation_package_id"),"preparation_token_id":prep_token.get("token_id"),"use_limit":1,"token_purpose":TOKEN_PURPOSE,"reason_codes":reasons(rs)}; return finish("mutauth-token-elig","mutation_authorization_token_eligibility","token_eligibility_id",body)

def issue_mutation_authorization_token(eligibility,verification,decision,scope,pkg,prep_token,authorization_sequence=0):
    rs=[]
    if eligibility.get("status")!="eligible": rs.append("token_not_eligible")
    body={"status":"issued" if not rs else "not_issued","authorization_verification_id":verification.get("verification_id"),"authorization_verification_fingerprint":verification.get("fingerprint"),"authorization_decision_id":decision.get("decision_id"),"authorization_decision_fingerprint":decision.get("fingerprint"),"authorized_scope_id":scope.get("authorized_scope_id"),"authorized_scope_fingerprint":scope.get("fingerprint"),"mutation_package_id":pkg.get("mutation_package_id"),"mutation_package_fingerprint":pkg.get("fingerprint"),"preparation_token_id":prep_token.get("token_id"),"preparation_token_fingerprint":prep_token.get("fingerprint"),"workspace_id":scope.get("workspace_id"),"workspace_root_fingerprint":scope.get("workspace_root_fingerprint"),"authorized_operation_fingerprints":scope.get("authorized_operation_fingerprints",[]),"authorization_sequence":authorization_sequence,"use_limit":1,"token_purpose":TOKEN_PURPOSE,"token_state":"issued" if not rs else "not_issued","token_consumed":False,"transaction_started":False,"mutation_performed":False,"not_authentication_credential":True,"not_bearer_token":True,"not_api_token":True,"not_session_token":True,"not_network_authority":True,"not_external_system_authority":True,"reason_codes":reasons(rs)}; return finish("mutauth-token","mutation_authorization_token","token_id",body)

def build_mutation_transaction_policy(p=None):
    p=mapping(p); rs=[]; body={"status":"active","allowed_operation_classes":seq(p.get("allowed_operation_classes")) or ["create_text_file","replace_text_file","delete_file","rename_path"],"maximum_transaction_operations":p.get("maximum_transaction_operations",100),"maximum_files":p.get("maximum_files",100),"maximum_content_bytes":p.get("maximum_content_bytes",1000000),"maximum_diff_entries":p.get("maximum_diff_entries",10000),"allowed_path_prefixes":seq(p.get("allowed_path_prefixes")),"required_precondition_modes":seq(p.get("required_precondition_modes")),"require_exact_before_fingerprint":True,"require_exact_workspace_identity":True,"require_authorization_verification":True,"require_one_time_authorization_token":True,"authorization_token_use_limit":1,"transaction_mode":"planning_only","atomicity_mode":p.get("atomicity_mode","all_or_nothing"),"backup_mode":p.get("backup_mode","metadata_only"),"rollback_mode":p.get("rollback_mode","metadata_only_reverse"),"commit_mode":p.get("commit_mode","future_boundary_only"),"recovery_mode":p.get("recovery_mode","metadata_only_manual_review"),"maximum_backup_artifacts":p.get("maximum_backup_artifacts",100),"maximum_rollback_operations":p.get("maximum_rollback_operations",100),"maximum_recovery_steps":p.get("maximum_recovery_steps",20),"allow_partial_transaction":bool(p.get("allow_partial_transaction",False)),"allow_git":False,"allow_shell":False,"allow_external_tools":False,"allow_symlink":False,"allow_binary":False}
    for k in ("maximum_transaction_operations","maximum_files","maximum_content_bytes","maximum_diff_entries","maximum_backup_artifacts","maximum_rollback_operations","maximum_recovery_steps"):
        if type(body[k]) is not int or body[k]<0: rs.append(k+"_invalid")
    body["status"]="invalid" if rs else "active"; body["reason_codes"]=reasons(rs); return finish("mutx-policy","mutation_transaction_policy","policy_id",body)

def admit_mutation_transaction(policy,verification,token_elig,token,scope,pkg,validation,prep_token):
    rs=[]; c=counts(scope.get("authorized_operations",[]))
    if policy.get("status")!="active": rs.append("policy_invalid")
    if verification.get("status")!="verified": rs.append("authorization_not_verified")
    if token_elig.get("status")!="eligible" or token.get("token_state")!="issued": rs.append("authorization_token_invalid")
    if scope.get("status")!="sealed": rs.append("authorized_scope_empty")
    if validation.get("status")!="valid": rs.append("package_validation_invalid")
    if token.get("token_consumed") is not False or prep_token.get("token_consumed") is not False: rs.append("token_consumed")
    if any(x.get("operation_type") not in policy.get("allowed_operation_classes",[]) for x in scope.get("authorized_operations",[])): rs.append("operation_class_not_allowed")
    if c["operation_count"]>policy.get("maximum_transaction_operations",0): rs.append("operation_bound_exceeded")
    if c["file_count"]>policy.get("maximum_files",0): rs.append("file_bound_exceeded")
    if c["content_byte_total"]>policy.get("maximum_content_bytes",0): rs.append("content_bound_exceeded")
    if c["diff_entry_total"]>policy.get("maximum_diff_entries",0): rs.append("diff_bound_exceeded")
    rs += conflicts(scope.get("authorized_operations",[]))
    return finish("mutx-admission","mutation_transaction_admission","admission_id",{"status":"admitted" if not rs else "not_admitted","policy_id":policy.get("policy_id"),"authorization_verification_id":verification.get("verification_id"),"authorization_token_id":token.get("token_id"),"authorized_scope_id":scope.get("authorized_scope_id"),"mutation_package_id":pkg.get("mutation_package_id"),"workspace_id":scope.get("workspace_id"),"workspace_root_fingerprint":scope.get("workspace_root_fingerprint"),"transaction_started":False,"mutation_performed":False,"reason_codes":reasons(rs)})

def build_mutation_transaction_plan(admission,pkg,token,scope):
    rs=[]
    if admission.get("status")!="admitted": rs.append("transaction_not_admitted")
    steps=[]
    for i,o in enumerate(scope.get("authorized_operations",[])):
        steps.append({"step_sequence":i,"prepared_operation_id":o.get("operation_id"),"prepared_operation_fingerprint":o.get("operation_fingerprint"),"authorized_operation_id":o.get("operation_id"),"authorized_operation_fingerprint":o.get("operation_fingerprint"),"operation_type":o.get("operation_type"),"source_path_fingerprint":o.get("source_path_fingerprint"),"target_path_fingerprint":o.get("target_path_fingerprint"),"content_fingerprint":o.get("content_fingerprint"),"diff_fingerprint":o.get("diff_fingerprint"),"precondition_fingerprint":o.get("precondition_fingerprint"),"expected_before_fingerprint":o.get("expected_before_fingerprint"),"expected_after_fingerprint":o.get("expected_after_fingerprint")})
    return finish("mutx-plan","mutation_transaction_plan","transaction_plan_id",{"status":"planned" if not rs else "not_planned","transaction_admission_id":admission.get("admission_id"),"transaction_admission_fingerprint":admission.get("fingerprint"),"mutation_package_id":pkg.get("mutation_package_id"),"mutation_package_fingerprint":pkg.get("fingerprint"),"authorization_token_id":token.get("token_id"),"authorization_token_fingerprint":token.get("fingerprint"),"authorized_scope_id":scope.get("authorized_scope_id"),"authorized_scope_fingerprint":scope.get("fingerprint"),"workspace_id":scope.get("workspace_id"),"workspace_root_fingerprint":scope.get("workspace_root_fingerprint"),"execution_session_id":pkg.get("execution_session_id"),"ordered_transaction_steps":steps,"transaction_mode":"planning_only","executable":False,"transaction_started":False,"mutation_performed":False,"reason_codes":reasons(rs)})

def build_mutation_atomicity_plan(plan,policy):
    rs=[] if plan.get("status")=="planned" and policy.get("atomicity_mode")=="all_or_nothing" else ["atomicity_policy_invalid"]
    return finish("atomicity-plan","mutation_atomicity_plan","atomicity_plan_id",{"status":"planned" if not rs else "invalid","transaction_plan_id":plan.get("transaction_plan_id"),"transaction_plan_fingerprint":plan.get("fingerprint"),"atomicity_mode":policy.get("atomicity_mode"),"ordered_validation_phase":[s.get("step_sequence") for s in plan.get("ordered_transaction_steps",[])],"ordered_staging_phase":[s.get("step_sequence") for s in plan.get("ordered_transaction_steps",[])],"ordered_commit_phase":[s.get("step_sequence") for s in plan.get("ordered_transaction_steps",[])],"failure_boundary_identifiers":["before_commit","during_commit","after_commit"],"required_invariant_checkpoints":["precondition","staging","pre_commit","post_commit"],"all_or_nothing_requirement":True,"partial_commit_allowed":False,"visibility_before_commit_allowed":False,"execution_performed":False,"reason_codes":reasons(rs)})

def build_mutation_backup_plan(plan,policy):
    ops=[s for s in plan.get("ordered_transaction_steps",[]) if s.get("operation_type") in ("replace_text_file","delete_file","rename_path")]; status="planned" if ops else "not_required"; return finish("backup-plan","mutation_backup_plan","backup_plan_id",{"status":status,"transaction_plan_id":plan.get("transaction_plan_id"),"transaction_plan_fingerprint":plan.get("fingerprint"),"operations_requiring_before_state_capture":[s.get("authorized_operation_id") for s in ops],"before_content_fingerprint_requirements":[s.get("expected_before_fingerprint") for s in ops],"backup_artifact_identity_formulas":["backup-"+str(s.get("authorized_operation_fingerprint"))[:16] for s in ops],"maximum_backup_count":policy.get("maximum_backup_artifacts"),"maximum_backup_bytes":policy.get("maximum_content_bytes"),"backup_retention_mode":"future_executor_scoped","backup_verification_requirements":["fingerprint_match"],"backup_created":False,"filesystem_read_performed":False,"filesystem_write_performed":False,"reason_codes":[]})

def build_mutation_rollback_plan(plan,backup):
    rev=list(reversed(plan.get("ordered_transaction_steps",[]))); return finish("rollback-plan","mutation_rollback_plan","rollback_plan_id",{"status":"planned" if rev else "not_required","transaction_plan_id":plan.get("transaction_plan_id"),"transaction_plan_fingerprint":plan.get("fingerprint"),"backup_plan_id":backup.get("backup_plan_id"),"backup_plan_fingerprint":backup.get("fingerprint"),"reverse_operation_sequence":[s.get("authorized_operation_id") for s in rev],"rollback_operation_types":["undo_"+str(s.get("operation_type")) for s in rev],"original_before_fingerprint_requirements":[s.get("expected_before_fingerprint") for s in rev],"backup_artifact_references":backup.get("backup_artifact_identity_formulas",[]),"rollback_precondition_references":[s.get("precondition_fingerprint") for s in rev],"rollback_verification_requirements":["before_fingerprint_restored","workspace_identity_unchanged"],"rollback_performed":False,"filesystem_write_performed":False,"reason_codes":[]})

def define_mutation_commit_boundary(plan,atomicity,backup,rollback):
    rs=[] if all([plan.get("status")=="planned", atomicity.get("status")=="planned", rollback.get("status") in ("planned","not_required")]) else ["commit_boundary_linkage_invalid"]
    body={"status":"defined" if not rs else "invalid","transaction_plan_id":plan.get("transaction_plan_id"),"transaction_plan_fingerprint":plan.get("fingerprint"),"atomicity_plan_id":atomicity.get("atomicity_plan_id"),"atomicity_plan_fingerprint":atomicity.get("fingerprint"),"backup_plan_id":backup.get("backup_plan_id"),"backup_plan_fingerprint":backup.get("fingerprint"),"rollback_plan_id":rollback.get("rollback_plan_id"),"rollback_plan_fingerprint":rollback.get("fingerprint"),"pre_commit_verification_requirements":["authorization_token_unconsumed","preconditions_match","backup_requirements_satisfied"],"commit_sequence":[s.get("step_sequence") for s in plan.get("ordered_transaction_steps",[])],"commit_visibility_policy":"invisible_until_future_executor_commit","commit_authorized":False,"commit_started":False,"commit_completed":False,"mutation_performed":False,"reason_codes":reasons(rs)}; out=finish("commit-boundary","mutation_commit_boundary","commit_boundary_id",body); out["commit_boundary_fingerprint"]=out["fingerprint"]; return out

def build_mutation_recovery_plan(plan,backup,rollback,commit_boundary,policy):
    rs=[] if commit_boundary.get("status")=="defined" else ["commit_boundary_invalid"]
    return finish("recovery-plan","mutation_recovery_plan","recovery_plan_id",{"status":"planned" if not rs else "invalid","transaction_plan_id":plan.get("transaction_plan_id"),"backup_plan_id":backup.get("backup_plan_id"),"rollback_plan_id":rollback.get("rollback_plan_id"),"commit_boundary_id":commit_boundary.get("commit_boundary_id"),"recoverable_failure_classes":["precondition_mismatch","staging_failure","commit_interruption"],"recovery_decision_codes":["manual_review_required","rollback_required"],"required_backup_verification":True,"required_rollback_verification":True,"required_post_recovery_workspace_verification":True,"manual_review_required_conditions":["any_failure"],"maximum_recovery_steps":policy.get("maximum_recovery_steps"),"recovery_performed":False,"retry_performed":False,"rollback_performed":False,"compensation_performed":False,"reason_codes":reasons(rs)})

def assemble_mutation_transaction_package(policy,request,eligibility,decision,scope,verification,token_elig,token,tx_policy,admission,plan,atomicity,backup,rollback,commit_boundary,recovery,pkg,validation,transaction_sequence=0):
    rs=[]
    if admission.get("status")!="admitted" or plan.get("status")!="planned": rs.append("transaction_components_invalid")
    c=counts(scope.get("authorized_operations",[]))
    body={"status":"packaged" if not rs else "invalid","mutation_package_id":pkg.get("mutation_package_id"),"mutation_package_fingerprint":pkg.get("fingerprint"),"package_validation_id":validation.get("validation_id"),"package_validation_fingerprint":validation.get("fingerprint"),"authorization_policy_reference":ref(policy,"policy_id"),"authorization_request_reference":ref(request,"request_id"),"authorization_eligibility_reference":ref(eligibility,"eligibility_id"),"authorization_decision_reference":ref(decision,"decision_id"),"authorized_scope_reference":ref(scope,"authorized_scope_id"),"authorization_verification_reference":ref(verification,"verification_id"),"authorization_token_eligibility_reference":ref(token_elig,"token_eligibility_id"),"authorization_token_reference":ref(token,"token_id"),"transaction_policy_reference":ref(tx_policy,"policy_id"),"transaction_admission_reference":ref(admission,"admission_id"),"transaction_plan_reference":ref(plan,"transaction_plan_id"),"atomicity_plan_reference":ref(atomicity,"atomicity_plan_id"),"backup_plan_reference":ref(backup,"backup_plan_id"),"rollback_plan_reference":ref(rollback,"rollback_plan_id"),"commit_boundary_reference":ref(commit_boundary,"commit_boundary_id"),"recovery_plan_reference":ref(recovery,"recovery_plan_id"),"workspace_id":scope.get("workspace_id"),"workspace_root_fingerprint":scope.get("workspace_root_fingerprint"),"execution_session_id":pkg.get("execution_session_id"),"ordered_transaction_steps":plan.get("ordered_transaction_steps",[]),"operation_references":scope.get("authorized_operation_fingerprints",[]),"content_references":scope.get("authorized_content_fingerprints",[]),"diff_references":scope.get("authorized_diff_fingerprints",[]),"precondition_references":scope.get("authorized_precondition_fingerprints",[]),"scope_constraints":scope.get("authorized_path_prefixes",[]),"authority_constraints":scope.get("authorized_authority_constraints",[]),**c,"transaction_sequence":transaction_sequence,"package_mode":"transaction_planning_only","transaction_authorized":not rs and bool(scope.get("authorized_operation_ids")),"transaction_started":False,"authorization_token_consumed":False,"preparation_token_consumed":False,"backup_created":False,"commit_started":False,"commit_completed":False,"rollback_performed":False,"recovery_performed":False,"mutation_executor_invoked":False,"mutation_performed":False,"filesystem_write_performed":False,"patch_applied":False,"git_invoked":False,"shell_invoked":False,"runtime_kernel_invoked":False,"reason_codes":reasons(rs)}; return finish("mutx-package","mutation_transaction_package","transaction_package_id",body)

def validate_mutation_transaction_package(tx_package,scope,verification,token,admission,plan,atomicity,backup,rollback,commit_boundary,recovery):
    rs=[]
    if tx_package.get("status")!="packaged": rs.append("transaction_package_invalid")
    if verification.get("status")!="verified": rs.append("authorization_verification_invalid")
    if token.get("token_purpose")!=TOKEN_PURPOSE or token.get("use_limit")!=1: rs.append("token_purpose_or_limit_invalid")
    if admission.get("status")!="admitted": rs.append("admission_invalid")
    if plan.get("ordered_transaction_steps")!=tx_package.get("ordered_transaction_steps"): rs.append("operation_mismatch")
    if rollback.get("reverse_operation_sequence") != list(reversed([s.get("authorized_operation_id") for s in plan.get("ordered_transaction_steps",[])])): rs.append("rollback_mismatch")
    if tx_package.get("workspace_id")!=scope.get("workspace_id"): rs.append("workspace_drift")
    rs += false_invariants(tx_package,token,plan,backup,rollback,commit_boundary,recovery)
    rs += conflicts(scope.get("authorized_operations",[]))
    return finish("mutx-validation","mutation_transaction_package_validation","validation_id",{"status":"valid" if not rs else "rejected","transaction_package_id":tx_package.get("transaction_package_id"),"transaction_package_fingerprint":tx_package.get("fingerprint"),"authorization_verification_id":verification.get("verification_id"),"authorization_token_id":token.get("token_id"),"transaction_plan_id":plan.get("transaction_plan_id"),"workspace_id":tx_package.get("workspace_id"),"reason_codes":reasons(rs)})

def verify_mutation_transaction_readiness(tx_package,tx_validation,verification,token_elig,token,tx_policy,admission,plan,atomicity,backup,rollback,commit_boundary,recovery):
    rs=[]
    for cond,code in [(tx_package.get("status")=="packaged","package_invalid"),(tx_validation.get("status")=="valid","package_validation_invalid"),(verification.get("status")=="verified","authorization_invalid"),(token_elig.get("status")=="eligible","token_eligibility_invalid"),(token.get("token_state")=="issued","token_not_issued"),(tx_policy.get("status")=="active","policy_invalid"),(admission.get("status")=="admitted","admission_invalid"),(plan.get("status")=="planned","plan_invalid"),(atomicity.get("status")=="planned","atomicity_invalid"),(rollback.get("status") in ("planned","not_required"),"rollback_invalid"),(commit_boundary.get("status")=="defined","commit_boundary_invalid"),(recovery.get("status")=="planned","recovery_invalid")]:
        if not cond: rs.append(code)
    if token.get("token_consumed") is not False: rs.append("consumed_token")
    if commit_boundary.get("commit_authorized") is not False: rs.append("commit_authorized")
    rs += false_invariants(tx_package,token,plan,backup,rollback,commit_boundary,recovery)
    return finish("mutx-ready","mutation_transaction_readiness","readiness_id",{"status":"ready" if not rs else "not_ready","transaction_package_id":tx_package.get("transaction_package_id"),"transaction_package_fingerprint":tx_package.get("fingerprint"),"transaction_package_validation_id":tx_validation.get("validation_id"),"transaction_package_validation_fingerprint":tx_validation.get("fingerprint"),"authorization_token_id":token.get("token_id"),"authorization_token_fingerprint":token.get("fingerprint"),"workspace_id":tx_package.get("workspace_id"),"workspace_root_fingerprint":tx_package.get("workspace_root_fingerprint"),"transaction_started":False,"commit_authorized":False,"commit_started":False,"mutation_executor_invoked":False,"mutation_performed":False,"filesystem_write_performed":False,"patch_applied":False,"git_invoked":False,"shell_invoked":False,"runtime_kernel_invoked":False,"reason_codes":reasons(rs)})

def build_mutation_executor_handoff(tx_package,tx_validation,readiness,token,prep_token,pkg,decision,scope,plan,atomicity,backup,rollback,commit_boundary,recovery):
    rs=[]
    if readiness.get("status")!="ready": rs.append("readiness_not_ready")
    body={"status":"handed_off" if not rs else "not_handed_off","transaction_package_id":tx_package.get("transaction_package_id"),"transaction_package_fingerprint":tx_package.get("fingerprint"),"transaction_package_validation_id":tx_validation.get("validation_id"),"transaction_package_validation_fingerprint":tx_validation.get("fingerprint"),"transaction_readiness_id":readiness.get("readiness_id"),"transaction_readiness_fingerprint":readiness.get("fingerprint"),"mutation_authorization_token_id":token.get("token_id"),"mutation_authorization_token_fingerprint":token.get("fingerprint"),"preparation_token_id":prep_token.get("token_id"),"preparation_token_fingerprint":prep_token.get("fingerprint"),"mutation_package_id":pkg.get("mutation_package_id"),"mutation_package_fingerprint":pkg.get("fingerprint"),"authorization_decision_id":decision.get("decision_id"),"authorization_decision_fingerprint":decision.get("fingerprint"),"authorized_scope_id":scope.get("authorized_scope_id"),"authorized_scope_fingerprint":scope.get("fingerprint"),"workspace_id":scope.get("workspace_id"),"workspace_root_fingerprint":scope.get("workspace_root_fingerprint"),"execution_session_id":pkg.get("execution_session_id"),"transaction_plan_id":plan.get("transaction_plan_id"),"transaction_plan_fingerprint":plan.get("fingerprint"),"atomicity_plan_id":atomicity.get("atomicity_plan_id"),"atomicity_plan_fingerprint":atomicity.get("fingerprint"),"backup_plan_id":backup.get("backup_plan_id"),"backup_plan_fingerprint":backup.get("fingerprint"),"rollback_plan_id":rollback.get("rollback_plan_id"),"rollback_plan_fingerprint":rollback.get("fingerprint"),"commit_boundary_id":commit_boundary.get("commit_boundary_id"),"commit_boundary_fingerprint":commit_boundary.get("fingerprint"),"recovery_plan_id":recovery.get("recovery_plan_id"),"recovery_plan_fingerprint":recovery.get("fingerprint"),"operation_count":len(scope.get("authorized_operation_ids",[])),"ordered_operation_fingerprints":scope.get("authorized_operation_fingerprints",[]),"content_fingerprints":scope.get("authorized_content_fingerprints",[]),"diff_fingerprints":scope.get("authorized_diff_fingerprints",[]),"precondition_fingerprints":scope.get("authorized_precondition_fingerprints",[]),"scope_constraints":scope.get("authorized_path_prefixes",[]),"authority_constraints":scope.get("authorized_authority_constraints",[]),"human_mutation_authorization_obtained":True,"transaction_planning_completed":True,"transaction_execution_authorized":False,"authorization_token_consumed":False,"preparation_token_consumed":False,"mutation_executor_invoked":False,"transaction_started":False,"backup_created":False,"commit_started":False,"commit_completed":False,"rollback_performed":False,"recovery_performed":False,"mutation_performed":False,"filesystem_write_performed":False,"patch_applied":False,"git_invoked":False,"shell_invoked":False,"runtime_kernel_invoked":False,"reason_codes":reasons(rs)}; return finish("mutx-handoff","mutation_executor_handoff","handoff_id",body)

def build_mutation_transaction_evidence(*arts):
    data={}
    for a in arts:
        if isinstance(a,dict):
            for k,v in a.items():
                if k.endswith("_id") or k in ("schema","status","fingerprint","workspace_id","token_purpose","use_limit","reason_codes") or "fingerprint" in k:
                    data.setdefault(k, v)
    data["false_invariant_codes"]=[k for k in FALSE_FLAGS]
    data["prohibited_payload_reason_codes"]=prohibited(data)
    return finish("mutx-evidence","mutation_transaction_evidence","evidence_id",{"status":"recorded","evidence":data,"reason_codes":[]})

def close_mutation_transaction(handoff,tx_package,tx_validation,readiness,verification,token_elig,token,admission,plan,atomicity,backup,rollback,commit_boundary,recovery,evidence):
    rs=[]
    for a,st,code in [(handoff,"handed_off","handoff_invalid"),(tx_package,"packaged","package_invalid"),(tx_validation,"valid","validation_invalid"),(readiness,"ready","readiness_invalid"),(verification,"verified","authorization_invalid"),(token_elig,"eligible","token_eligibility_invalid"),(token,"issued","token_invalid"),(admission,"admitted","admission_invalid"),(plan,"planned","plan_invalid"),(atomicity,"planned","atomicity_invalid"),(commit_boundary,"defined","commit_boundary_invalid"),(recovery,"planned","recovery_invalid")]:
        if a.get("status")!=st: rs.append(code)
    rs += false_invariants(handoff,tx_package,readiness,token,plan,backup,rollback,commit_boundary,recovery)
    return finish("mutx-closure","mutation_transaction_closure","closure_id",{"status":"closed" if not rs else "not_closed","handoff_id":handoff.get("handoff_id"),"transaction_package_id":tx_package.get("transaction_package_id"),"transaction_package_validation_id":tx_validation.get("validation_id"),"transaction_readiness_id":readiness.get("readiness_id"),"authorization_verification_id":verification.get("verification_id"),"authorization_token_id":token.get("token_id"),"evidence_id":evidence.get("evidence_id"),"mutation_authorization_and_transaction_planning_complete":not rs,"passive_mutation_executor_handoff_exists":handoff.get("status")=="handed_off","transaction_execution_authorized":False,"token_consumed":False,"transaction_started":False,"backup_created":False,"commit_started":False,"commit_completed":False,"rollback_performed":False,"recovery_performed":False,"mutation_performed":False,"filesystem_write_performed":False,"patch_applied":False,"git_invoked":False,"shell_invoked":False,"runtime_kernel_invoked":False,"reason_codes":reasons(rs)})
