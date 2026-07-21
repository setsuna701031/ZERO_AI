from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence
import json, os, tempfile

from core.engineering.engineering_runtime_orchestrator_common import canonical_json, fingerprint, SAFE_RELATIVE

SESSION_SCHEMA="zero.engineering.runtime_session.v1"
CYCLE_SCHEMA="zero.engineering.runtime_cycle.v1"
CANDIDATE_SCHEMA="zero.engineering.proposal_candidate.v1"
JOURNAL_SCHEMA="zero.engineering.runtime_session_journal_entry.v1"
CHECKPOINT_SCHEMA="zero.engineering.runtime_session_checkpoint.v1"
STATUSES=("created","active","awaiting_approval","awaiting_authorization","ready_for_execution","executing","awaiting_verification","verifying","awaiting_feedback","awaiting_next_proposal","blocked","failed","completed","closed","invalid")
TERMINAL={"completed","closed","failed","invalid"}
EVENTS=("session_objective_defined","cycle_objectives_assigned","objective_progress_evaluated","completion_readiness_evaluated","completion_review_requested","completion_decision_recorded","iteration_health_evaluated","next_iteration_objective_candidate_created","session_created","cycle_admitted","approval_observed","authorization_observed","execution_started","execution_completed","verification_started","verification_completed","feedback_recorded","proposal_candidate_created","cycle_closed","session_resumed","session_blocked","session_failed","session_completed","session_closed")
REQUIRED_REF_KEYS=("schema","artifact_identity","artifact_fingerprint")

class RuntimeSessionError(ValueError): pass

def _seal(body:Mapping[str,Any], fp_field:str, id_field:str, prefix:str)->dict[str,Any]:
    out={k:v for k,v in body.items() if k not in {fp_field,id_field}}
    fp=fingerprint(out); out[fp_field]=fp
    if id_field=="session_id":
        seed={"repository_identity":out.get("repository_identity"),"task_identity":out.get("task_identity"),"schema":out.get("schema")}
        out[id_field]=prefix+fingerprint(seed)[:24]
    else:
        out[id_field]=prefix+fp[:24]
    return out

def _verify_seal(value:Mapping[str,Any], fp_field:str, id_field:str, prefix:str)->None:
    if not isinstance(value,Mapping): raise RuntimeSessionError("artifact_not_mapping")
    base={k:v for k,v in value.items() if k not in {fp_field,id_field}}
    fp=fingerprint(base)
    if value.get(fp_field)!=fp: raise RuntimeSessionError("fingerprint_mismatch")
    if id_field=="session_id":
        seed={"repository_identity":value.get("repository_identity"),"task_identity":value.get("task_identity"),"schema":value.get("schema")}
        expected=prefix+fingerprint(seed)[:24]
    else:
        expected=prefix+fp[:24]
    if value.get(id_field)!=expected: raise RuntimeSessionError("identity_mismatch")

def _ref(value:Mapping[str,Any]|None,name:str,required:bool=False)->dict[str,Any]|None:
    if value is None:
        if required: raise RuntimeSessionError(f"{name}_required")
        return None
    if not isinstance(value,Mapping): raise RuntimeSessionError(f"{name}_not_mapping")
    if str(value.get("schema","" )).startswith("zero.test."): raise RuntimeSessionError(f"{name}_fake_schema")
    missing=[k for k in REQUIRED_REF_KEYS if not value.get(k)]
    if missing: raise RuntimeSessionError(f"{name}_missing_reference_fields")
    return {"schema":str(value["schema"]),"artifact_identity":str(value["artifact_identity"]),"artifact_fingerprint":str(value["artifact_fingerprint"])}

def create_engineering_runtime_session(repository_identity:Mapping[str,Any], task_identity:Mapping[str,Any])->dict[str,Any]:
    if not isinstance(repository_identity,Mapping) or not repository_identity.get("repository_id") or not repository_identity.get("repository_fingerprint"):
        raise RuntimeSessionError("invalid_repository_identity")
    if not isinstance(task_identity,Mapping) or not (task_identity.get("task_id") or task_identity.get("engineering_intent_id")):
        raise RuntimeSessionError("invalid_task_identity")
    body={"schema":SESSION_SCHEMA,"repository_identity":dict(repository_identity),"task_identity":dict(task_identity),"status":"created","current_cycle_number":0,"cycle_count":0,"cycle_references":[],"latest_cycle_reference":None,"session_lineage":{"root_session_id":None,"parent_session_id":None},"resume_state":{"decision":"requires_human_approval"},"inspection_state":{"cycle_lineage_valid":True},"closure_state":{"closed":False}}
    return _seal(body,"session_fingerprint","session_id","engineering-runtime-session-")

def build_proposal_candidate(session:Mapping[str,Any], cycle:Mapping[str,Any], verification_reference:Mapping[str,Any], feedback_reference:Mapping[str,Any], *, objective:str, bounded_scope:Sequence[str])->dict[str,Any]:
    body={"schema":CANDIDATE_SCHEMA,"source_session_id":session.get("session_id"),"source_cycle_id":cycle.get("cycle_id"),"source_cycle_number":cycle.get("cycle_number"),"verification_evidence_reference":_ref(verification_reference,"verification_evidence",True),"feedback_evidence_reference":_ref(feedback_reference,"feedback_evidence",True),"identified_issue_or_improvement_objective":str(objective),"bounded_proposed_scope":list(bounded_scope),"candidate_only":True,"not_approved":True,"not_authorized":True,"not_executable":True}
    return _seal(body,"candidate_fingerprint","proposal_candidate_id","engineering-proposal-candidate-")

def build_engineering_runtime_cycle(*, session_id:str, cycle_number:int, previous_cycle:Mapping[str,Any]|None=None, proposal_reference:Mapping[str,Any]|None=None, approval_reference:Mapping[str,Any]|None=None, authorization_reference:Mapping[str,Any]|None=None, execution_session_reference:Mapping[str,Any]|None=None, execution_result_reference:Mapping[str,Any]|None=None, verification_runtime_reference:Mapping[str,Any]|None=None, verification_result_reference:Mapping[str,Any]|None=None, feedback_reference:Mapping[str,Any]|None=None, new_proposal_candidate_reference:Mapping[str,Any]|None=None, cycle_status:str|None=None, cycle_closure_reference:Mapping[str,Any]|None=None)->dict[str,Any]:
    if cycle_number<1: raise RuntimeSessionError("invalid_cycle_number")
    prev_id=previous_cycle.get("cycle_id") if previous_cycle else None; prev_fp=previous_cycle.get("cycle_fingerprint") if previous_cycle else None
    status=cycle_status or _derive_cycle_status(approval_reference,authorization_reference,execution_result_reference,verification_result_reference,feedback_reference,new_proposal_candidate_reference,cycle_closure_reference)
    body={"schema":CYCLE_SCHEMA,"session_id":session_id,"cycle_number":cycle_number,"previous_cycle_id":prev_id,"previous_cycle_fingerprint":prev_fp,"proposal_reference":_ref(proposal_reference,"proposal",True),"approval_reference":_ref(approval_reference,"approval"),"authorization_reference":_ref(authorization_reference,"authorization"),"execution_session_reference":_ref(execution_session_reference,"execution_session"),"execution_result_reference":_ref(execution_result_reference,"execution_result"),"verification_runtime_reference":_ref(verification_runtime_reference,"verification_runtime"),"verification_result_reference":_ref(verification_result_reference,"verification_result"),"feedback_reference":_ref(feedback_reference,"feedback"),"new_proposal_candidate_reference":_ref(new_proposal_candidate_reference,"new_proposal_candidate"),"cycle_status":status,"cycle_closure_reference":_ref(cycle_closure_reference,"cycle_closure")}
    return _seal(body,"cycle_fingerprint","cycle_id","engineering-runtime-cycle-")

def _derive_cycle_status(a,z,e,v,f,cand,cl):
    if cl: return "closed"
    if v and not f: return "awaiting_feedback"
    if e and not v: return "awaiting_verification"
    if z and not e: return "ready_for_execution"
    if a and not z: return "awaiting_authorization"
    return "awaiting_approval"

def validate_cycle_linkage(session:Mapping[str,Any], cycle:Mapping[str,Any])->None:
    _verify_seal(cycle,"cycle_fingerprint","cycle_id","engineering-runtime-cycle-")
    if cycle.get("schema")!=CYCLE_SCHEMA or cycle.get("session_id")!=session.get("session_id"): raise RuntimeSessionError("cycle_session_mismatch")
    refs=session.get("cycle_references") or []
    if any(r.get("artifact_identity")==cycle.get("cycle_id") for r in refs): raise RuntimeSessionError("duplicate_cycle")
    expected=len(refs)+1
    if cycle.get("cycle_number")!=expected: raise RuntimeSessionError("cycle_ordering_invalid")
    if expected==1:
        if cycle.get("previous_cycle_id") or cycle.get("previous_cycle_fingerprint"): raise RuntimeSessionError("first_cycle_previous_link_forbidden")
    else:
        prev=refs[-1]
        if cycle.get("previous_cycle_id")!=prev.get("artifact_identity") or cycle.get("previous_cycle_fingerprint")!=prev.get("artifact_fingerprint"): raise RuntimeSessionError("previous_cycle_linkage_invalid")
    if cycle.get("approval_reference") and any(cycle.get("approval_reference")==r.get("approval_reference") for r in session.get("cycle_lineage_debug",[])): raise RuntimeSessionError("approval_reuse_forbidden")

def _cycle_ref(c:Mapping[str,Any])->dict[str,Any]: return {"schema":c["schema"],"artifact_identity":c["cycle_id"],"artifact_fingerprint":c["cycle_fingerprint"],"cycle_number":c["cycle_number"]}

def append_engineering_runtime_cycle(session:Mapping[str,Any], cycle:Mapping[str,Any])->dict[str,Any]:
    if session.get("status") in TERMINAL: raise RuntimeSessionError("terminal_session_cannot_append")
    validate_engineering_runtime_session(session); validate_cycle_linkage(session,cycle)
    prior=session.get("cycle_lineage_debug",[])
    for p in prior:
        if cycle.get("approval_reference") and cycle.get("approval_reference")==p.get("approval_reference"): raise RuntimeSessionError("approval_reuse_forbidden")
        if cycle.get("authorization_reference") and cycle.get("authorization_reference")==p.get("authorization_reference"): raise RuntimeSessionError("authorization_reuse_forbidden")
    body={k:v for k,v in session.items() if k not in {"session_fingerprint","session_id"}}
    body["cycle_count"]=len(session.get("cycle_references") or [])+1; body["current_cycle_number"]=cycle["cycle_number"]; body["cycle_references"]=[*session.get("cycle_references",[]),_cycle_ref(cycle)]; body["latest_cycle_reference"]=_cycle_ref(cycle); body["status"]=derive_engineering_runtime_session_state([*prior,cycle]); body["cycle_lineage_debug"]=[*prior,cycle]
    return _seal(body,"session_fingerprint","session_id","engineering-runtime-session-")

def derive_engineering_runtime_session_state(cycles:Sequence[Mapping[str,Any]])->str:
    if not cycles: return "created"
    last=cycles[-1]
    if last.get("cycle_status")=="closed": return "awaiting_next_proposal"
    return {"awaiting_approval":"awaiting_approval","awaiting_authorization":"awaiting_authorization","ready_for_execution":"ready_for_execution","awaiting_verification":"awaiting_verification","awaiting_feedback":"awaiting_feedback"}.get(last.get("cycle_status"),"active")

def complete_session(session:Mapping[str,Any])->dict[str,Any]:
    if session.get("cycle_count",0)<3: raise RuntimeSessionError("three_cycles_required")
    body={k:v for k,v in session.items() if k not in {"session_fingerprint","session_id"}}; body["status"]="completed"; body["resume_state"]={"decision":"already_completed"}; return _seal(body,"session_fingerprint","session_id","engineering-runtime-session-")

def close_engineering_runtime_session(session:Mapping[str,Any])->dict[str,Any]:
    if session.get("status")!="completed": raise RuntimeSessionError("only_completed_session_can_close")
    body={k:v for k,v in session.items() if k not in {"session_fingerprint","session_id"}}; body["status"]="closed"; body["closure_state"]={"closed":True}; body["resume_state"]={"decision":"already_closed"}; return _seal(body,"session_fingerprint","session_id","engineering-runtime-session-")

def validate_engineering_runtime_session(session:Mapping[str,Any])->None:
    _verify_seal(session,"session_fingerprint","session_id","engineering-runtime-session-")
    if session.get("schema")!=SESSION_SCHEMA or session.get("status") not in STATUSES: raise RuntimeSessionError("invalid_session")

def determine_next_governed_action(session:Mapping[str,Any])->str:
    return {"created":"admit_cycle","awaiting_approval":"requires_human_approval","awaiting_authorization":"requires_authorization","ready_for_execution":"requires_execution","awaiting_verification":"requires_verification","awaiting_feedback":"requires_feedback_review","awaiting_next_proposal":"requires_new_proposal","completed":"close_session","closed":"none"}.get(session.get("status"),"blocked")

def make_journal_entry(session_id:str, sequence_number:int, event_type:str, cycle_number:int|None, artifact_reference:Mapping[str,Any]|None, previous_entry_fingerprint:str|None, derived_session_status:str)->dict[str,Any]:
    if event_type not in EVENTS: raise RuntimeSessionError("invalid_event_type")
    body={"schema":JOURNAL_SCHEMA,"session_id":session_id,"sequence_number":sequence_number,"event_type":event_type,"cycle_number":cycle_number,"artifact_reference":_ref(artifact_reference,"journal_artifact") if artifact_reference else None,"previous_entry_fingerprint":previous_entry_fingerprint,"derived_session_status":derived_session_status}
    return _seal(body,"entry_fingerprint","journal_entry_id","engineering-runtime-journal-entry-")

def validate_journal(entries:Sequence[Mapping[str,Any]], session_id:str)->None:
    prev=None; seen=set()
    for i,e in enumerate(entries,1):
        _verify_seal(e,"entry_fingerprint","journal_entry_id","engineering-runtime-journal-entry-")
        if e.get("session_id")!=session_id or e.get("sequence_number")!=i or e.get("previous_entry_fingerprint")!=prev or e.get("journal_entry_id") in seen: raise RuntimeSessionError("journal_chain_invalid")
        seen.add(e["journal_entry_id"]); prev=e["entry_fingerprint"]

def replay_journal(entries:Sequence[Mapping[str,Any]], session_id:str)->dict[str,Any]:
    validate_journal(entries,session_id); return {"session_id":session_id,"event_count":len(entries),"journal_head":entries[-1]["entry_fingerprint"] if entries else None,"events":[e["event_type"] for e in entries]}

def inspect_engineering_runtime_session(session:Mapping[str,Any], cycles:Sequence[Mapping[str,Any]], checkpoint:Mapping[str,Any]|None=None)->dict[str,Any]:
    validate_engineering_runtime_session(session)
    completed=sum(1 for c in cycles if c.get("cycle_status")=="closed")
    v4=checkpoint.get("v3_4_objective_coordination",{}) if checkpoint else {}
    return {"session_id":session["session_id"],"session_status":session["status"],"repository_identity":session["repository_identity"],"current_cycle":session.get("current_cycle_number"),"cycle_count":session.get("cycle_count"),"completed_cycles":completed,"blocked_cycles":sum(1 for c in cycles if c.get("cycle_status")=="blocked"),"failed_cycles":sum(1 for c in cycles if c.get("cycle_status")=="failed"),"pending_governance_stage":determine_next_governed_action(session),"next_governed_action":determine_next_governed_action(session),"resumability":resume_decision(session,cycles,checkpoint)["decision"],"latest_durable_checkpoint":checkpoint.get("checkpoint_fingerprint") if checkpoint else None,"session_fingerprint_verification":"valid","cycle_lineage_verification":"valid","objective_count":v4.get("objective_count",0),"required_objective_count":v4.get("required_objective_count",0),"satisfied_objective_count":v4.get("satisfied_objective_count",0),"remaining_objective_count":v4.get("remaining_objective_count",0),"current_iteration_health":v4.get("iteration_health","not_initialized"),"completion_readiness":v4.get("completion_readiness","not_initialized"),"completion_candidate":v4.get("completion_candidate",False),"human_completion_review_required":v4.get("human_completion_review_required",False),"next_iteration_recommendation":v4.get("next_iteration_recommendation","objective_coordination_unavailable"),"timeline":[_timeline(c) for c in cycles]}

def _timeline(c):
    steps=["Proposal"]
    if c.get("approval_reference"): steps.append("Approved")
    else: steps.append("Awaiting Approval")
    if c.get("authorization_reference"): steps.append("Authorized")
    if c.get("execution_result_reference"): steps.append("Executed")
    if c.get("verification_result_reference"): steps.append("Verified")
    if c.get("feedback_reference"): steps.append("Feedback")
    if c.get("cycle_status")=="closed": steps.append("Closed")
    return {"cycle_number":c.get("cycle_number"),"line":" → ".join(steps)}

def build_checkpoint(session:Mapping[str,Any], cycles:Sequence[Mapping[str,Any]], journal_entries:Sequence[Mapping[str,Any]])->dict[str,Any]:
    body={"schema":CHECKPOINT_SCHEMA,"session_id":session["session_id"],"session_status":session["status"],"session_fingerprint":session["session_fingerprint"],"current_cycle":session.get("current_cycle_number"),"cycle_references":session.get("cycle_references",[]),"journal_head":journal_entries[-1]["entry_fingerprint"] if journal_entries else None,"latest_verified_artifact_references":[c.get("verification_result_reference") for c in cycles if c.get("verification_result_reference")],"resume_metadata":{"next_governed_action":determine_next_governed_action(session)},"v3_4_objective_coordination":session.get("v3_4_objective_coordination",{"status":"not_initialized"})}
    return _seal(body,"checkpoint_fingerprint","checkpoint_id","engineering-runtime-checkpoint-")

def resume_decision(session:Mapping[str,Any], cycles:Sequence[Mapping[str,Any]], checkpoint:Mapping[str,Any]|None=None)->dict[str,Any]:
    try:
        validate_engineering_runtime_session(session)
        if checkpoint and checkpoint.get("session_fingerprint")!=session.get("session_fingerprint"): raise RuntimeSessionError("checkpoint_session_fingerprint_mismatch")
        for i,c in enumerate(cycles,1):
            _verify_seal(c,"cycle_fingerprint","cycle_id","engineering-runtime-cycle-")
            if c.get("cycle_number")!=i: raise RuntimeSessionError("cycle_ordering_invalid")
    except Exception as exc:
        return {"decision":"invalid","reason":str(exc),"will_approve":False,"will_authorize":False,"will_execute":False}
    if session.get("status")=="closed": d="already_closed"
    elif session.get("status")=="completed": d="already_completed"
    elif session.get("status")=="blocked": d="blocked"
    elif checkpoint and (checkpoint.get("v3_4_objective_coordination") or {}).get("resume_decision"): d=(checkpoint.get("v3_4_objective_coordination") or {}).get("resume_decision")
    else: d=determine_next_governed_action(session)
    return {"decision":d,"will_approve":False,"will_authorize":False,"will_execute":False,"will_create_proposal":False,"will_complete":False}

class RuntimeSessionStore:
    def __init__(self,root:str|Path): self.root=Path(root)
    def _base(self,session_id):
        if not SAFE_RELATIVE.fullmatch(session_id): raise RuntimeSessionError("unsafe_session_id")
        return self.root/session_id
    def _write(self,path:Path,value:Mapping[str,Any],overwrite=False):
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists() and not overwrite: raise RuntimeSessionError("artifact_exists")
        fd,tmp=tempfile.mkstemp(prefix=".runtime-session-",suffix=".json",dir=path.parent)
        try:
            with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as f: f.write(canonical_json(value)+"\n"); f.flush(); os.fsync(f.fileno())
            os.replace(tmp,path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
        if self._read(path)!=value: raise RuntimeSessionError("readback_mismatch")
    def _read(self,path:Path):
        try: value=json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc: raise RuntimeSessionError("corrupt_json") from exc
        if canonical_json(value)+"\n"!=path.read_text(encoding="utf-8"): raise RuntimeSessionError("non_canonical_json")
        return value
    def create(self,session): self._write(self._base(session["session_id"])/"session.json",session); return self.save_index(session["session_id"])
    def save_cycle(self,cycle): self._write(self._base(cycle["session_id"])/"cycles"/f"cycle-{cycle['cycle_number']:04d}.json",cycle); return self.save_index(cycle["session_id"])
    def save_objective(self,obj): self._write(self._base(obj["session_id"])/"objectives"/f"{obj['objective_id']}.json",obj); return self.save_index(obj["session_id"])
    def save_assignment(self,a): self._write(self._base(a["session_id"])/"assignments"/f"cycle-{a['cycle_number']:04d}.json",a); return self.save_index(a["session_id"])
    def save_progress(self,p): self._write(self._base(p["session_id"])/"progress"/f"cycle-{p['cycle_number']:04d}.json",p,overwrite=True); return self.save_index(p["session_id"])
    def save_completion(self,c): self._write(self._base(c["session_id"])/"completion"/f"{c.get('readiness_id') or c.get('review_request_id') or c.get('decision_id')}.json",c); return self.save_index(c["session_id"])
    def save_iteration_health(self,h): self._write(self._base(h["session_id"])/"iteration-health"/"latest.json",h,overwrite=True); return self.save_index(h["session_id"])
    def save_next_objective_candidate(self,c): self._write(self._base(c["session_id"])/"next-objective-candidates"/f"{c['candidate_id']}.json",c); return self.save_index(c["session_id"])
    def save_checkpoint(self,checkpoint): self._write(self._base(checkpoint["session_id"])/"checkpoints"/"latest.json",checkpoint,overwrite=True); return self.save_index(checkpoint["session_id"])
    def append_journal(self,entry): self._write(self._base(entry["session_id"])/"journal"/f"entry-{entry['sequence_number']:06d}.json",entry); return self.save_index(entry["session_id"])
    def load(self,session_id):
        base=self._base(session_id)
        if not base.exists(): raise RuntimeSessionError("session_not_found")
        session=self._read(base/"session.json"); cycles=[self._read(p) for p in sorted((base/"cycles").glob("cycle-*.json"))] if (base/"cycles").exists() else []
        journal=[self._read(p) for p in sorted((base/"journal").glob("entry-*.json"))] if (base/"journal").exists() else []
        checkpoint=self._read(base/"checkpoints"/"latest.json") if (base/"checkpoints"/"latest.json").exists() else None
        objectives=[self._read(p) for p in sorted((base/"objectives").glob("*.json"))] if (base/"objectives").exists() else []
        assignments=[self._read(p) for p in sorted((base/"assignments").glob("*.json"))] if (base/"assignments").exists() else []
        progress=[self._read(p) for p in sorted((base/"progress").glob("*.json"))] if (base/"progress").exists() else []
        completion=[self._read(p) for p in sorted((base/"completion").glob("*.json"))] if (base/"completion").exists() else []
        health=self._read(base/"iteration-health"/"latest.json") if (base/"iteration-health"/"latest.json").exists() else None
        next_candidates=[self._read(p) for p in sorted((base/"next-objective-candidates").glob("*.json"))] if (base/"next-objective-candidates").exists() else []
        return {"session":session,"cycles":cycles,"journal":journal,"checkpoint":checkpoint,"objectives":objectives,"assignments":assignments,"progress":progress,"completion":completion,"iteration_health":health,"next_objective_candidates":next_candidates,"index":self._read(base/"index.json") if (base/"index.json").exists() else None}
    def save_index(self,session_id):
        base=self._base(session_id); files=sorted(str(p.relative_to(base)).replace('\\','/') for p in base.rglob('*.json') if p.name!="index.json")
        index={"schema":"zero.engineering.runtime_session_index.v1","session_id":session_id,"files":files}
        self._write(base/"index.json",index,overwrite=True); return index
