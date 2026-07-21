from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from core.engineering.engineering_runtime_orchestrator_common import SAFE_RELATIVE, canonical_json, fingerprint, prohibited
from core.engineering.engineering_runtime_session import build_engineering_runtime_session
from core.engineering.engineering_runtime_session_store import read_session_artifact, write_session_artifact, load_session_store

REQUEST_SCHEMA = "zero.engineering.work_request.v1"
INTAKE_SCHEMA = "zero.engineering.work_intake.v1"
COORDINATION_SCHEMA = "zero.engineering.work_coordination.v1"
HANDOFF_SCHEMA = "zero.engineering.work_human_gate_handoff.v1"
JOURNAL_SCHEMA = "zero.engineering.work_journal.v1"
CHECKPOINT_SCHEMA = "zero.engineering.work_checkpoint.v1"
MODES = {"analysis_only", "plan_only", "proposal_only", "governed_delivery", "inspection", "resume"}
STAGES = ("intake","repository_admission","repository_analysis","objective_definition","planning","proposal_preparation","proposal_review","awaiting_approval","awaiting_authorization","execution_preparation","ready_for_execution","execution","verification","progress_evaluation","completion_review","next_iteration","completed","blocked","failed","closed","invalid")
FLOW = list(STAGES[:15])
REQUIRED = {"repository_admission":"repository_admission","objective_definition":"repository_analysis_closure","planning":"objective","proposal_preparation":"planning_closure","proposal_review":"proposal","awaiting_approval":"proposal_review_closure","awaiting_authorization":"approval_closure","execution_preparation":"authorization_closure","ready_for_execution":"execution_preparation_closure","execution":"execution_readiness","verification":"execution_result","progress_evaluation":"verification_closure","completion_review":"progress_evaluation"}
DECISIONS = {"intake":"requires_repository_admission","repository_admission":"requires_repository_analysis","repository_analysis":"requires_objective_definition","objective_definition":"requires_planning","planning":"requires_proposal_preparation","proposal_preparation":"requires_proposal_review","proposal_review":"requires_human_approval","awaiting_approval":"requires_human_approval","awaiting_authorization":"requires_authorization","execution_preparation":"requires_execution_preparation","ready_for_execution":"requires_execution","execution":"requires_execution","verification":"requires_verification","progress_evaluation":"requires_progress_evaluation","completion_review":"requires_completion_review","next_iteration":"requires_next_iteration_proposal","completed":"already_completed","closed":"already_closed","blocked":"blocked","failed":"blocked","invalid":"invalid"}
AUTH_KEYS = {"approval","approved","approval_closure","authorization","authorized","authorization_closure","execution_token","mutation_token","authority","authority_state"}

class WorkEntryError(ValueError):
    def __init__(self, code: str):
        super().__init__(code); self.code = code

def _stable(body: Mapping[str, Any], fp_key: str, id_key: str, prefix: str) -> dict[str, Any]:
    base = {k:v for k,v in dict(body).items() if k not in {fp_key, id_key}}
    fp = fingerprint(base); return {**base, fp_key: fp, id_key: prefix + fp[:32]}

def _verify(a: Mapping[str, Any], schema: str, fp_key: str, id_key: str) -> None:
    if not isinstance(a, Mapping) or a.get("schema") != schema: raise WorkEntryError("schema_invalid")
    if str(a.get("schema", "")).startswith("zero.test."): raise WorkEntryError("fake_schema_rejected")
    expected = _stable(a, fp_key, id_key, str(a.get(id_key, "")).rsplit("-",1)[0]+"-")
    if expected.get(fp_key) != a.get(fp_key) or expected.get(id_key) != a.get(id_key): raise WorkEntryError("artifact_fingerprint_mismatch")

def _safe_scope(scope: Sequence[str], name="scope") -> list[str]:
    if not isinstance(scope, Sequence) or isinstance(scope, (str, bytes)) or not scope: raise WorkEntryError(f"empty_{name}_rejection")
    out = sorted({str(x).strip() for x in scope if str(x).strip()})
    if not out or any(x in {"*",".","/"} or x.startswith(("/","../")) or ".." in x.split("/") for x in out): raise WorkEntryError("unbounded_scope_rejection")
    return out

def _ref(a: Mapping[str, Any], fp_key: str|None=None) -> dict[str, Any]:
    if str(a.get("schema","")).startswith("zero.test."): raise WorkEntryError("fake_artifact_reference")
    ids = [k for k in a if k.endswith("_id")]
    fps = [fp_key] if fp_key else [k for k in a if k.endswith("fingerprint") or k == "fingerprint"]
    if not ids or not fps or not a.get(fps[0]): raise WorkEntryError("artifact_reference_missing")
    return {"schema":a.get("schema"),"artifact_identity":a.get(ids[0]),"artifact_fingerprint":a.get(fps[0]),"session_id":a.get("session_id")}

def create_engineering_work_request(*, request_statement: str, repository_identity: Mapping[str, Any], repository_root_reference: str, requested_scope: Sequence[str], excluded_scope: Sequence[str]=(), constraints: Sequence[str]=(), acceptance_intent: str="human_review", risk_classification: str="standard", requested_mode: str="governed_delivery", source_actor_reference: Mapping[str, Any]|None=None) -> dict[str, Any]:
    if not str(request_statement).strip(): raise WorkEntryError("empty_request_rejection")
    if requested_mode not in MODES: raise WorkEntryError("invalid_mode_rejection")
    if not repository_identity: raise WorkEntryError("repository_identity_missing")
    root = str(repository_root_reference).strip()
    if not root or root.startswith(("/","\\")) or ".." in root.split("/") or not SAFE_RELATIVE.fullmatch(root): raise WorkEntryError("unsafe_repository_root_rejection")
    scope = _safe_scope(requested_scope); excluded = sorted(set(str(x) for x in excluded_scope if str(x)))
    payload = {"request_statement":request_statement,"repository_identity":dict(repository_identity),"repository_root_reference":root,"requested_scope":scope,"excluded_scope":excluded,"constraints":list(constraints),"acceptance_intent":acceptance_intent,"risk_classification":risk_classification,"requested_mode":requested_mode,"source_actor_reference":dict(source_actor_reference or {})}
    low=canonical_json(payload).lower()
    if prohibited(payload) or any(k in low for k in AUTH_KEYS) or any(x in low for x in ("shell_fragment","command")): raise WorkEntryError("authority_payload_rejection")
    return _stable({"schema":REQUEST_SCHEMA, **payload}, "work_request_fingerprint", "work_request_id", "engineering-work-request-")

def admit_engineering_work(req: Mapping[str, Any]) -> dict[str, Any]:
    _verify(req, REQUEST_SCHEMA, "work_request_fingerprint", "work_request_id")
    if prohibited(req): raise WorkEntryError("prohibited_payload_rejection")
    body={"schema":INTAKE_SCHEMA,"work_request_reference":_ref(req,"work_request_fingerprint"),"admission_status":"admitted","normalized_intent":req["request_statement"].strip(),"bounded_scope":list(req["requested_scope"]),"repository_admission_reference":{"repository_identity":req["repository_identity"],"repository_root_reference":req["repository_root_reference"],"status":"admitted"},"risk_summary":{"risk_classification":req["risk_classification"]},"governance_requirements":{"approval_required":True,"authorization_required":True,"mutation_authority_granted":False},"next_stage":"repository_admission"}
    return _stable(body,"intake_fingerprint","intake_id","engineering-work-intake-")

def create_work_coordination(req: Mapping[str, Any], intake: Mapping[str, Any], runtime_session: Mapping[str, Any]|None=None) -> dict[str, Any]:
    _verify(req, REQUEST_SCHEMA,"work_request_fingerprint","work_request_id"); _verify(intake, INTAKE_SCHEMA,"intake_fingerprint","intake_id")
    sess = dict(runtime_session or build_engineering_runtime_session({"request_id":req["work_request_id"],"fingerprint":req["work_request_fingerprint"],"workspace_id":fingerprint(req["repository_identity"])[:24],"workspace_root_fingerprint":fingerprint(req["repository_root_reference"]),"session_sequence":1}))
    body={"schema":COORDINATION_SCHEMA,"work_request_reference":_ref(req,"work_request_fingerprint"),"work_intake_reference":_ref(intake,"intake_fingerprint"),"runtime_session_reference":_ref(sess),"current_stage":"intake","stage_artifact_references":{"intake":_ref(intake,"intake_fingerprint")},"completed_stages":[],"pending_stage":"repository_admission","next_governed_action":"requires_repository_admission","coordination_status":"active"}
    return _stable(body,"coordination_fingerprint","coordination_id","engineering-work-coordination-")

def derive_next_governed_action(coord: Mapping[str, Any]) -> str: return DECISIONS.get(str(coord.get("current_stage")), "invalid")

def advance_work_coordination(coord: Mapping[str, Any], artifact: Mapping[str, Any], artifact_key: str) -> dict[str, Any]:
    _verify(coord, COORDINATION_SCHEMA,"coordination_fingerprint","coordination_id")
    stage = coord["current_stage"]
    if stage in {"completed","closed","failed","invalid"}: raise WorkEntryError("terminal_coordination_rejected")
    idx = FLOW.index(stage); target = FLOW[idx+1]
    need = REQUIRED.get(target)
    if need and need != artifact_key and need not in coord.get("stage_artifact_references", {}): raise WorkEntryError(f"{target}_missing_required_artifact")
    if artifact.get("session_id") not in (None, coord["runtime_session_reference"].get("artifact_identity")): raise WorkEntryError("mixed_session_rejection")
    refs = dict(coord.get("stage_artifact_references",{})); refs[artifact_key]=_ref(artifact)
    completed = sorted(set(list(coord.get("completed_stages",[]))+[stage]))
    body={k:v for k,v in coord.items() if k not in {"coordination_fingerprint","coordination_id"}}
    body.update({"current_stage":target,"stage_artifact_references":refs,"completed_stages":completed,"pending_stage":None if target in {"completed","closed"} else target,"next_governed_action":DECISIONS[target],"coordination_status":"blocked" if target in {"blocked","failed","invalid"} else "active"})
    return _stable(body,"coordination_fingerprint","coordination_id","engineering-work-coordination-")

def create_human_gate_handoff(coord: Mapping[str, Any]) -> dict[str, Any]:
    _verify(coord, COORDINATION_SCHEMA,"coordination_fingerprint","coordination_id")
    if coord.get("current_stage") != "awaiting_approval": raise WorkEntryError("human_gate_requires_awaiting_approval")
    body={"schema":HANDOFF_SCHEMA,"coordination_reference":_ref(coord,"coordination_fingerprint"),"runtime_session_reference":coord["runtime_session_reference"],"proposal_reference":coord["stage_artifact_references"].get("proposal"),"proposal_review_reference":coord["stage_artifact_references"].get("proposal_review_closure"),"requested_human_action":"approve","risk_summary":{},"scope_summary":{},"evidence_summary":{},"authority_state":"not_granted"}
    return _stable(body,"handoff_fingerprint","handoff_id","engineering-work-human-gate-")

def inspect_work_coordination(coord: Mapping[str, Any]) -> dict[str, Any]:
    _verify(coord, COORDINATION_SCHEMA,"coordination_fingerprint","coordination_id")
    done=set(coord.get("completed_stages",[])); cur=coord["current_stage"]
    cur_i = FLOW.index(cur) if cur in FLOW else len(FLOW)
    timeline=[{"stage":s,"status":"Completed" if s in done else "Current" if s==cur else "Pending" if FLOW.index(s)>cur_i else "Not Started"} for s in FLOW]
    return {"work_request_id":coord["work_request_reference"]["artifact_identity"],"coordination_id":coord["coordination_id"],"runtime_session_id":coord["runtime_session_reference"]["artifact_identity"],"coordination_status":coord["coordination_status"],"current_stage":cur,"completed_stages":coord["completed_stages"],"pending_stage":coord.get("pending_stage"),"next_governed_action":derive_next_governed_action(coord),"missing_artifacts":[REQUIRED.get(cur)] if REQUIRED.get(cur) and REQUIRED.get(cur) not in coord.get("stage_artifact_references",{}) else [],"timeline":timeline,"approval_status":"pending" if cur=="awaiting_approval" else "not_started","authorization_status":"not_started","execution_status":"not_started","verification_status":"not_started","completion_readiness":coord.get("completion_readiness","not_evaluated"),"iteration_health":coord.get("iteration_health","not_evaluated"),"resumability":"resumable","human_action_required":cur in {"awaiting_approval","completion_review","next_iteration","blocked"}}

def resume_work_coordination(coord: Mapping[str, Any]) -> dict[str, Any]:
    ins=inspect_work_coordination(coord); cur=ins["current_stage"]
    decision = "requires_human_approval" if cur=="awaiting_approval" else DECISIONS.get(cur,"invalid")
    return {"decision":decision,"resumable":decision not in {"invalid","already_closed"},"next_governed_action":decision,"will_approve":False,"will_authorize":False,"will_execute":False,"will_complete":False,"will_create_proposal_automatically":False,"inspection":ins}

def persist_work_entry(root: str|Path, session_id: str, *, request=None, intake=None, coordination=None, handoff=None) -> dict[str, Any]:
    files=[]
    for name,val in (("work-entry/request.json",request),("work-entry/intake.json",intake),("work-entry/coordination.json",coordination),("work-entry/human-gate-handoff.json",handoff)):
        if val is not None: write_session_artifact(root, session_id, name, val); assert read_session_artifact(root, session_id, name)==val; files.append(name)
    return {"persisted_files":files,"work_entry_status":"initialized" if files else "not_initialized"}

def make_journal(coord: Mapping[str, Any], events: Sequence[str]) -> dict[str, Any]:
    head=""
    rows=[]
    for i,e in enumerate(events,1):
        head=fingerprint({"previous":head,"sequence":i,"event":e,"coordination_id":coord["coordination_id"]}); rows.append({"sequence":i,"event":e,"journal_head":head})
    return _stable({"schema":JOURNAL_SCHEMA,"coordination_reference":_ref(coord,"coordination_fingerprint"),"events":rows,"journal_head":head},"journal_fingerprint","journal_id","engineering-work-journal-")

def make_checkpoint(coord: Mapping[str, Any], journal: Mapping[str, Any]|None=None) -> dict[str, Any]:
    body={"schema":CHECKPOINT_SCHEMA,"coordination_reference":_ref(coord,"coordination_fingerprint"),"current_stage":coord["current_stage"],"runtime_session_reference":coord["runtime_session_reference"],"latest_stage_artifacts":coord.get("stage_artifact_references",{}),"journal_head":(journal or {}).get("journal_head"),"next_governed_action":derive_next_governed_action(coord),"resume_metadata":{"decision":resume_work_coordination(coord)["decision"]}}
    return _stable(body,"checkpoint_fingerprint","checkpoint_id","engineering-work-checkpoint-")
