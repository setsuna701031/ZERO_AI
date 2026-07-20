from __future__ import annotations
from copy import deepcopy
from typing import Any, Mapping
from core.engineering.engineering_execution_session import create_engineering_execution_session, seal_session, validate_engineering_execution_session, REFS
from core.engineering.engineering_task_artifact_adapter_registry import default_registry
from core.engineering.engineering_governed_workspace_mutation_executor import execute_pipeline
from core.engineering.engineering_completion_foundation import build_completion

class EngineeringExecutionError(ValueError): pass

def _id(a: Mapping[str, Any], *names: str) -> Any:
    for n in names:
        if a.get(n): return a.get(n)
    return a.get("artifact_identity")
def _fp(a: Mapping[str, Any]) -> Any: return a.get("fingerprint") or a.get("artifact_fingerprint")
def _set_ref(s: Mapping[str, Any], name: str, artifact: Mapping[str, Any], *ids: str) -> dict[str, Any]:
    cur=deepcopy(dict(s)); ik,fk=REFS[name]; ni=_id(artifact,*ids); nf=_fp(artifact)
    if cur.get(ik) and (cur.get(ik)!=ni or cur.get(fk)!=nf): raise EngineeringExecutionError("conflicting_replay")
    cur[ik]=ni; cur[fk]=nf
    cur["replay_count"] = int(cur.get("replay_count",0)) + (1 if s.get(ik)==ni else 0)
    sealed=seal_session(cur); _ensure_valid(sealed); return sealed
def _ensure_valid(s):
    r=validate_engineering_execution_session(s)
    if not r["valid"]: raise EngineeringExecutionError("invalid_session:"+",".join(r["errors"]))
def _phase_validate(phase: str, artifact: Mapping[str, Any]) -> None:
    try: default_registry().validate_artifact(phase, dict(artifact))
    except Exception as exc: raise EngineeringExecutionError("invalid_"+phase+":"+str(exc)) from exc

def create_execution_session(*, task: Mapping[str, Any], proposal: Mapping[str, Any], proposal_linkage: Mapping[str, Any]) -> dict[str, Any]:
    _phase_validate("proposal", proposal); _phase_validate("proposal_linkage", proposal_linkage)
    return create_engineering_execution_session(task=task, proposal=proposal, proposal_linkage=proposal_linkage)

def attach_approval(session, approval):
    if session.get("current_stage")!="awaiting_approval" and not session.get("approval_identity"): raise EngineeringExecutionError("approval_stage_invalid")
    _phase_validate("approval", approval)
    if approval.get("proposal_identity") and approval.get("proposal_identity")!=session.get("proposal_identity"): raise EngineeringExecutionError("approval_proposal_mismatch")
    return _set_ref(session,"approval",approval,"approval_decision_id")
def attach_authorization(session, authorization):
    if not session.get("approval_identity"): raise EngineeringExecutionError("authorization_before_approval")
    _phase_validate("authorization", authorization)
    if authorization.get("approval_identity") and authorization.get("approval_identity")!=session.get("approval_identity"): raise EngineeringExecutionError("authorization_approval_mismatch")
    return _set_ref(session,"authorization",authorization,"authorization_decision_id")
def attach_authorized_scope(session, authorized_scope):
    if not session.get("authorization_identity"): raise EngineeringExecutionError("scope_before_authorization")
    _phase_validate("authorized_scope", authorized_scope)
    return _set_ref(session,"authorized_scope",authorized_scope,"authorized_scope_id")
def attach_preparation(session, preparation):
    if not session.get("authorization_identity"): raise EngineeringExecutionError("preparation_before_authorization")
    _phase_validate("preparation", preparation)
    return _set_ref(session,"preparation",preparation,"closure_id")
def attach_token(session, token):
    if not session.get("preparation_identity"): raise EngineeringExecutionError("token_before_preparation")
    _phase_validate("preparation_token", token)
    return _set_ref(session,"token",token,"token_id")
def attach_execution_result(session, execution_result):
    if not session.get("token_identity"): raise EngineeringExecutionError("execution_before_token")
    _phase_validate("execution_result", execution_result)
    return _set_ref(session,"execution",execution_result,"result_id")
def execute_authorized_mutation(session, *, handoff: Mapping[str, Any], workspace_root: str, execute_confirmed: bool=True) -> tuple[dict[str, Any], Mapping[str, Any]]:
    if session.get("current_stage")!="ready_for_execution": raise EngineeringExecutionError("session_not_ready_for_execution")
    result = execute_pipeline(handoff, workspace_root, execute_confirmed=execute_confirmed)
    if "result" not in result: raise EngineeringExecutionError("governed_executor_failed")
    return attach_execution_result(session, result["result"]), result

def attach_verification_result(session, verification_result):
    if not session.get("execution_identity"): raise EngineeringExecutionError("verification_before_execution")
    _phase_validate("verification_result", verification_result)
    if verification_result.get("execution_identity")!=session.get("execution_identity"): raise EngineeringExecutionError("verification_execution_mismatch")
    return _set_ref(session,"verification_result",verification_result,"verification_result_id")
def complete_execution_session(session, *, completion: Mapping[str, Any]|None=None, task_id: str|None=None, repository_identity: Any=None, analysis_identity: str="", candidate_identity: str="", repair_plan: Mapping[str, Any]|None=None, proposal: Mapping[str, Any]|None=None, verification_result: Mapping[str, Any]|None=None):
    if not session.get("verification_result_identity"): raise EngineeringExecutionError("completion_before_verification")
    if completion is None:
        if not (repair_plan and proposal and verification_result): raise EngineeringExecutionError("completion_artifact_required")
        completion=build_completion(task_id=task_id or session.get("task_id"), repository_identity=repository_identity or session.get("repository_identity"), analysis_identity=analysis_identity, candidate_identity=candidate_identity, repair_plan=repair_plan, proposal=proposal, verification_result=verification_result)
    _phase_validate("completion", completion)
    return _set_ref(session,"completion",completion,"completion_id")
def close_execution_session(session, closure):
    if not session.get("completion_identity"): raise EngineeringExecutionError("closure_before_completion")
    return _set_ref(session,"closure",closure,"closure_id","task_closure_id")
def inspect_execution_session(session): _ensure_valid(session); return deepcopy(dict(session))
def resume_execution_session(session):
    cur=deepcopy(dict(session)); cur["current_stage"]="invalid_persisted_stage_ignored"; cur["resume_count"]=int(session.get("resume_count",0))+1; sealed=seal_session(cur); _ensure_valid(sealed); return sealed
