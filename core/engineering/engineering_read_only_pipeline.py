from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.engineering.engineering_runtime_orchestrator_common import SAFE_RELATIVE, canonical_json, fingerprint
from core.engineering.engineering_work_entry import (
    REQUEST_SCHEMA, INTAKE_SCHEMA, COORDINATION_SCHEMA, WorkEntryError,
    _verify as verify_work_artifact, _ref as work_ref, _stable as stable_work_artifact,
    create_human_gate_handoff, make_checkpoint, make_journal,
)
from core.engineering.engineering_runtime_session import build_engineering_runtime_session
from core.engineering.engineering_runtime_objectives_v4 import build_session_objective, validate_session_objective
from core.engineering.repository_root_admission import admit_repository_root, validate_repository_root_admission
from core.engineering.repository_snapshot import build_repository_snapshot, validate_repository_snapshot
from core.engineering.repository_topology import build_repository_topology, validate_repository_topology
from core.engineering.repository_discovery import build_repository_discoveries, validate_repository_language_discovery, validate_repository_build_discovery, validate_repository_test_discovery
from core.engineering.repository_dependency_analysis import build_repository_dependency_analysis, validate_repository_dependency_analysis
from core.engineering.repository_engineering_inventory import build_repository_engineering_inventory, validate_repository_engineering_inventory
from core.engineering.repository_analysis_evidence import build_repository_analysis_evidence, validate_repository_analysis_evidence
from core.engineering.repository_analysis_report import build_repository_analysis_report, validate_repository_analysis_report
from core.engineering.repository_analysis_closure import build_repository_analysis_closure, validate_repository_analysis_closure
from core.engineering.repository_analysis_common import artifact as analysis_artifact
from core.engineering.repository_scoped_analysis import normalize_scoped_repository_scope
from core.engineering.engineering_planning_context import build_engineering_planning_context
from core.engineering.engineering_goal_extraction import extract_engineering_goals
from core.engineering.engineering_work_breakdown import build_engineering_work_breakdown
from core.engineering.engineering_dependency_ordering import build_engineering_dependency_ordering
from core.engineering.engineering_validation_strategy import build_engineering_validation_strategy
from core.engineering.engineering_risk_assessment import build_engineering_risk_assessment
from core.engineering.engineering_plan import build_engineering_plan, validate_engineering_plan
from core.engineering.engineering_planning_verification import verify_engineering_plan
from core.engineering.engineering_planning_closure import build_engineering_planning_closure, validate_engineering_planning_closure
from core.engineering.engineering_proposal_intake import build_engineering_proposal_intake, OPAQUE_SCOPE
from core.engineering.engineering_proposal_scope import build_engineering_proposal_scope
from core.engineering.engineering_proposed_change_set import build_engineering_proposed_change_set
from core.engineering.engineering_proposal_dependency_mapping import build_engineering_proposal_dependency_mapping
from core.engineering.engineering_proposal_validation_plan import build_engineering_proposal_validation_plan
from core.engineering.engineering_proposal_risk_review import build_engineering_proposal_risk_review
from core.engineering.engineering_proposal import build_engineering_proposal, validate_engineering_proposal
from core.engineering.engineering_proposal_verification import verify_engineering_proposal
from core.engineering.engineering_proposal_closure import build_engineering_proposal_closure, validate_engineering_proposal_closure
from core.engineering.engineering_runtime_formal_persistence import validate_review_closure
from core.engineering.engineering_intake_common import identified

PIPELINE_SCHEMA="zero.engineering.read_only_pipeline.v1"
STAGE_SCHEMA="zero.engineering.read_only_stage_result.v1"
REQUESTED_MODES=("analysis_only","plan_only","proposal_only","governed_delivery")
PIPELINE_STATUSES={"created","running","awaiting_input","awaiting_human_approval","completed_read_only_preparation","blocked","failed","invalid"}
STAGE_STATUSES={"completed","awaiting_input","blocked","failed","invalid"}
STAGES=("repository_admission","repository_analysis","objective_definition","planning","proposal_preparation","proposal_review")
NEXT={"repository_admission":"requires_repository_analysis","repository_analysis":"requires_objective_definition","objective_definition":"requires_planning","planning":"requires_proposal_preparation","proposal_preparation":"requires_proposal_review","proposal_review":"requires_human_approval"}
MODE_STOP={"analysis_only":"repository_analysis","plan_only":"planning","proposal_only":"proposal_review","governed_delivery":"human_gate"}
STORE_FILES=("work-entry/pipeline.json","work-entry/stages/repository-admission.json","work-entry/stages/repository-analysis.json","work-entry/stages/objective-definition.json","work-entry/stages/planning.json","work-entry/stages/proposal-preparation.json","work-entry/stages/proposal-review.json","work-entry/checkpoint.json","work-entry/journal.json")

class ReadOnlyPipelineError(ValueError):
    def __init__(self, code:str): super().__init__(code); self.code=code

def _stable(body:Mapping[str,Any], fp_key:str, id_key:str, prefix:str)->dict[str,Any]:
    base={k:v for k,v in dict(body).items() if k not in {fp_key,id_key}}
    fp=fingerprint(base); return {**base, fp_key:fp, id_key:prefix+fp[:32]}

def _verify_stable(a:Mapping[str,Any], schema:str, fp_key:str, id_key:str, prefix:str):
    if not isinstance(a,Mapping) or a.get("schema")!=schema or str(a.get("schema","")).startswith("zero.test."): raise ReadOnlyPipelineError("invalid_artifact_reference")
    exp=_stable(a,fp_key,id_key,prefix)
    if exp.get(fp_key)!=a.get(fp_key) or exp.get(id_key)!=a.get(id_key): raise ReadOnlyPipelineError("artifact_fingerprint_mismatch")

def _reference(a:Mapping[str,Any], id_key:str|None=None, fp_key:str|None=None)->dict[str,Any]:
    if str(a.get("schema","")).startswith("zero.test."): raise ReadOnlyPipelineError("fake_artifact_reference")
    ids=[id_key] if id_key else [k for k in a if k.endswith("_id")]
    fps=[fp_key] if fp_key else [k for k in a if k.endswith("fingerprint") or k=="fingerprint"]
    if not ids or not fps or not a.get(ids[0]) or not a.get(fps[0]): raise ReadOnlyPipelineError("artifact_reference_missing")
    return {"schema":a.get("schema"),"artifact_identity":a.get(ids[0]),"artifact_fingerprint":a.get(fps[0]),"session_id":a.get("session_id")}

def _mode(req):
    m=req.get("requested_mode","governed_delivery")
    if m not in REQUESTED_MODES: raise ReadOnlyPipelineError("unsupported_requested_mode")
    return m

def create_read_only_pipeline(req:Mapping[str,Any], intake:Mapping[str,Any], coordination:Mapping[str,Any], *, existing_pipeline:Mapping[str,Any]|None=None)->dict[str,Any]:
    if existing_pipeline is not None: raise ReadOnlyPipelineError("duplicate_pipeline_rejection")
    verify_work_artifact(req,REQUEST_SCHEMA,"work_request_fingerprint","work_request_id"); verify_work_artifact(intake,INTAKE_SCHEMA,"intake_fingerprint","intake_id"); verify_work_artifact(coordination,COORDINATION_SCHEMA,"coordination_fingerprint","coordination_id")
    if coordination["work_request_reference"]["artifact_identity"]!=req["work_request_id"] or coordination["work_intake_reference"]["artifact_identity"]!=intake["intake_id"]: raise ReadOnlyPipelineError("coordination_lineage_mismatch")
    body={"schema":PIPELINE_SCHEMA,"work_request_reference":work_ref(req,"work_request_fingerprint"),"work_intake_reference":work_ref(intake,"intake_fingerprint"),"coordination_reference":work_ref(coordination,"coordination_fingerprint"),"runtime_session_reference":coordination["runtime_session_reference"],"requested_mode":_mode(req),"pipeline_status":"created","current_stage":"repository_admission","completed_stage_results":[],"pending_stage":"repository_admission","next_governed_action":"requires_repository_admission","missing_inputs":[],"blocked_reasons":[],"human_action_required":False,"mutation_authority":"not_granted"}
    return _stable(body,"pipeline_fingerprint","pipeline_id","engineering-read-only-pipeline-")

def build_stage_result(*, pipeline:Mapping[str,Any], coordination:Mapping[str,Any], stage:str, input_references:Sequence[Mapping[str,Any]], output_references:Sequence[Mapping[str,Any]], stage_status:str="completed", evidence_summary:Mapping[str,Any]|None=None, missing_inputs:Sequence[str]=(), blocked_reasons:Sequence[str]=(), next_stage:str|None=None)->dict[str,Any]:
    _verify_stable(pipeline,PIPELINE_SCHEMA,"pipeline_fingerprint","pipeline_id","engineering-read-only-pipeline-"); verify_work_artifact(coordination,COORDINATION_SCHEMA,"coordination_fingerprint","coordination_id")
    if stage not in STAGES or stage_status not in STAGE_STATUSES: raise ReadOnlyPipelineError("invalid_stage_enum")
    if stage_status=="completed" and not output_references: raise ReadOnlyPipelineError("completed_without_output_rejected")
    sid=coordination["runtime_session_reference"]["artifact_identity"]
    ins=[dict(r) for r in input_references]; outs=[dict(r) for r in output_references]
    for r in ins+outs:
        if r.get("session_id") not in (None,sid): raise ReadOnlyPipelineError("mixed_session_rejection")
        if str(r.get("schema","")).startswith("zero.test.") or not r.get("artifact_identity") or not r.get("artifact_fingerprint"): raise ReadOnlyPipelineError("invalid_artifact_reference")
    body={"schema":STAGE_SCHEMA,"pipeline_id":pipeline["pipeline_id"],"coordination_id":coordination["coordination_id"],"runtime_session_id":sid,"stage":stage,"input_references":ins,"output_references":outs,"validation_status":"valid" if stage_status=="completed" else stage_status,"stage_status":stage_status,"evidence_summary":dict(evidence_summary or {}),"missing_inputs":sorted(set(missing_inputs)),"blocked_reasons":sorted(set(blocked_reasons)),"next_stage":next_stage}
    return _stable(body,"stage_result_fingerprint","stage_result_id","engineering-read-only-stage-")

def _request_from_work(req:Mapping[str,Any])->dict[str,Any]:
    payload={"repository_identity":req["repository_identity"],"root_reference":req["repository_root_reference"],"scope_hints":req["requested_scope"],"excluded_scope":req.get("excluded_scope",[]),"analysis_mode":"read_only","read_only_authority":True}
    return analysis_artifact("zero.engineering.repository_analysis_request.v1","prepared",{"analysis_request_payload":payload,"reasons":["work_entry_read_only_pipeline"],"boundary":{"read_only":True,"mutation_authority":"not_granted"}},"repository_analysis_request_id","engineering-repository-analysis-request-")

def _analysis(req:Mapping[str,Any], root:Path)->dict[str,Any]:
    ar=_request_from_work(req); adm=admit_repository_root(root); 
    if adm.artifact.get("status")!="admitted": return {"status":"blocked","missing":["repository_root"],"artifacts":{"repository_analysis_request":ar,"repository_admission":adm.artifact}}
    scope=req.get("requested_scope",[]); excl=set(req.get("excluded_scope",[]))
    if any(x in {"*",".","/"} or x.startswith("/") or ".." in x.split("/") for x in scope): return {"status":"invalid","missing":["safe_scope"],"artifacts":{"repository_analysis_request":ar,"repository_admission":adm.artifact}}
    
    try: scoped=normalize_scoped_repository_scope(adm.root, scope)
    except ValueError: return {"status":"invalid","missing":["safe_scope"],"artifacts":{"repository_analysis_request":ar,"repository_admission":adm.artifact}}
    snap=build_repository_snapshot(adm, scoped_scope=scoped)
    topo=build_repository_topology(snap)
    lang,build,test=build_repository_discoveries(snap,topo,adm)
    dep=build_repository_dependency_analysis(snap,adm)
    inv=build_repository_engineering_inventory(snap,topo)
    ev=build_repository_analysis_evidence([ar,adm.artifact,snap,topo,lang,build,test,dep,inv])
    rep=build_repository_analysis_report(ar,adm.artifact,snap,topo,lang,build,test,dep,inv,ev)
    clo=build_repository_analysis_closure(ar,adm.artifact,snap,topo,lang,build,test,dep,inv,ev,rep)
    validators=(validate_repository_root_admission(adm.artifact),validate_repository_snapshot(snap),validate_repository_topology(topo,snap),validate_repository_language_discovery(lang,snap,topo),validate_repository_build_discovery(build,snap,topo),validate_repository_test_discovery(test,snap,topo),validate_repository_dependency_analysis(dep,snap),validate_repository_engineering_inventory(inv,snap,topo),validate_repository_analysis_evidence(ev,[ar,adm.artifact,snap,topo,lang,build,test,dep,inv]),validate_repository_analysis_report(rep,ev),validate_repository_analysis_closure(clo))
    if not all(v.valid for v in validators) or clo.get("status")!="closed": return {"status":"blocked","missing":["repository_analysis_closure"],"artifacts":{}}
    return {"status":"completed","artifacts":{"repository_analysis_request":ar,"repository_admission":adm.artifact,"repository_snapshot":snap,"repository_topology":topo,"repository_language_discovery":lang,"repository_build_discovery":build,"repository_test_discovery":test,"repository_dependency_analysis":dep,"repository_engineering_inventory":inv,"repository_analysis_evidence":ev,"repository_analysis_report":rep,"repository_analysis_closure":clo}}

def _objective(req, coord, closure):
    acc=str(req.get("acceptance_intent") or "").strip()
    if acc in {"","human_review"}: raise ReadOnlyPipelineError("missing_acceptance_criteria")
    sess=build_engineering_runtime_session({"request_id":req["work_request_id"],"fingerprint":req["work_request_fingerprint"],"workspace_id":fingerprint(req["repository_identity"])[:24],"workspace_root_fingerprint":fingerprint(req["repository_root_reference"]),"session_sequence":1})
    sess={**sess,"session_id":coord["runtime_session_reference"]["artifact_identity"]}
    obj=build_session_objective(sess,source_task_identity={"task_id":req["work_request_id"]},source_planning_reference=_reference(closure,"repository_analysis_closure_id","fingerprint"),objective_statement=req["request_statement"],bounded_scope=req["requested_scope"],acceptance_criteria=[{"criterion_id":"acceptance-intent","description":acc,"required":True,"evidence_type":"human_acceptance","verification_method":"human_review_gate"}],required_evidence=[])
    validate_session_objective(obj,sess); return obj

def _planning(req, closure):
    ctx=build_engineering_planning_context(closure,{},{"requested_scope":req["requested_scope"]})
    goals=extract_engineering_goals(ctx,{"goals":[{"title":"Governed read-only preparation","description":req["request_statement"],"evidence_references":ctx["evidence_references"],"affected_components":ctx["allowed_scope"]}]})
    work=build_engineering_work_breakdown(goals); deps=build_engineering_dependency_ordering(work); val=build_engineering_validation_strategy(goals,work); risks=build_engineering_risk_assessment(ctx,goals,work)
    plan=build_engineering_plan(ctx,goals,work,deps,val,risks); ver=verify_engineering_plan(plan); clo=build_engineering_planning_closure(plan,ver)
    if not validate_engineering_plan(plan).valid or not validate_engineering_planning_closure(clo).valid or clo.get("status")!="closed": raise ReadOnlyPipelineError("blocked_by_existing_contract")
    return {"engineering_plan":plan,"planning_verification":ver,"planning_closure":clo}

def _proposal(req, planning_closure):
    intent={"requested_scope":[OPAQUE_SCOPE],"excluded_scope":[],"constraints":{"read_only_pipeline":True}}
    intake=build_engineering_proposal_intake(planning_closure,intent); scope=build_engineering_proposal_scope(intake,intent); changes=build_engineering_proposed_change_set(scope,intent); deps=build_engineering_proposal_dependency_mapping(changes,[]); vals=build_engineering_proposal_validation_plan(changes,intent); risks=build_engineering_proposal_risk_review(changes,intake["evidence_references"],intent)
    prop=build_engineering_proposal(intake,scope,changes,deps,vals,risks); ver=verify_engineering_proposal(prop); clo=build_engineering_proposal_closure(prop,ver)
    if not validate_engineering_proposal(prop).valid or not validate_engineering_proposal_closure(clo).valid or clo.get("status")!="closed": raise ReadOnlyPipelineError("blocked_by_existing_contract")
    return {"proposal_intake":intake,"proposal_scope":scope,"proposed_change_set":changes,"proposal_dependency_mapping":deps,"proposal_validation_plan":vals,"proposal_risk_review":risks,"engineering_proposal":prop,"proposal_verification":ver,"proposal_closure":clo}

def _review(proposal_closure):
    body={"schema":"zero.engineering.proposal_review_closure.v1","status":"closed","engineering_proposal_review_id":"engineering-proposal-review-"+proposal_closure["fingerprint"][:24],"proposal_closure_id":proposal_closure["proposal_closure_id"],"engineering_proposal_id":proposal_closure["engineering_proposal_id"],"planning_closure_id":proposal_closure["planning_closure_id"],"repository_identity":proposal_closure["repository_identity"],"analyzed_revision":proposal_closure["analyzed_revision"],"governance_boundary_declaration":{"ready_for_approval":True,"approved":False,"authorization_granted":False,"execution_granted":False,"mutation_granted":False},"next_boundary_declaration":{"foundation":"Engineering Approval Foundation","requires_human_approval":True},"boundary":{"sealed":True}}
    rev=identified(body,"proposal_review_closure_id","engineering-proposal-review-closure-")
    if not validate_review_closure(rev).valid: raise ReadOnlyPipelineError("blocked_by_existing_contract")
    return rev

def _updated_pipeline(p, *, status, current, completed, pending, action, missing=(), blocked=(), human=False):
    body={k:v for k,v in p.items() if k not in {"pipeline_fingerprint","pipeline_id"}}
    body.update({"pipeline_status":status,"current_stage":current,"completed_stage_results":list(completed),"pending_stage":pending,"next_governed_action":action,"missing_inputs":sorted(set(missing)),"blocked_reasons":sorted(set(blocked)),"human_action_required":human,"mutation_authority":"not_granted"})
    return _stable(body,"pipeline_fingerprint","pipeline_id","engineering-read-only-pipeline-")

def run_next_read_only_stage(req, intake, coordination, pipeline, *, repository_root: str|Path|None=None, artifacts:Mapping[str,Any]|None=None):
    artifacts=dict(artifacts or {})
    stage=pipeline.get("current_stage")
    if stage not in STAGES: return {"pipeline":pipeline,"coordination":coordination,"artifacts":artifacts,"stage_result":None}
    inputs=[pipeline["work_request_reference"],pipeline["work_intake_reference"],pipeline["coordination_reference"]]
    try:
        if stage=="repository_admission":
            root=Path(repository_root or req["repository_root_reference"])
            result=_analysis(req,root); out=[_reference(result["artifacts"]["repository_admission"],"repository_root_admission_id","fingerprint")] if result["artifacts"].get("repository_admission") else []
            if result["status"]!="completed": sr=build_stage_result(pipeline=pipeline,coordination=coordination,stage=stage,input_references=inputs,output_references=out,stage_status="blocked",missing_inputs=result.get("missing",()),blocked_reasons=["missing_adapter"],next_stage=stage); return {"pipeline":_updated_pipeline(pipeline,status="blocked",current=stage,completed=pipeline["completed_stage_results"],pending=stage,action="blocked",missing=result.get("missing",()),blocked=["missing_adapter"]),"coordination":coordination,"artifacts":{**artifacts,**result["artifacts"]},"stage_result":sr}
            artifacts.update(result["artifacts"]); out=[_reference(artifacts["repository_admission"],"repository_root_admission_id","fingerprint")]; next_stage="repository_analysis"
        elif stage=="repository_analysis":
            clo=artifacts.get("repository_analysis_closure");
            if not clo or not validate_repository_analysis_closure(clo).valid: raise ReadOnlyPipelineError("manual_artifact_required")
            out=[_reference(clo,"repository_analysis_closure_id","fingerprint")]; next_stage="objective_definition"
        elif stage=="objective_definition":
            obj=_objective(req,coordination,artifacts["repository_analysis_closure"]); artifacts["objective"]=obj; out=[_reference(obj,"objective_id","objective_fingerprint")]; next_stage="planning"
        elif stage=="planning":
            artifacts.update(_planning(req,artifacts["repository_analysis_closure"])); out=[_reference(artifacts["planning_closure"],"planning_closure_id","fingerprint")]; next_stage="proposal_preparation"
        elif stage=="proposal_preparation":
            artifacts.update(_proposal(req,artifacts["planning_closure"])); out=[_reference(artifacts["engineering_proposal"],"engineering_proposal_id","fingerprint")]; next_stage="proposal_review"
        else:
            artifacts["proposal_review_closure"]=_review(artifacts["proposal_closure"]); out=[_reference(artifacts["proposal_review_closure"],"proposal_review_closure_id","fingerprint")]; next_stage="human_gate"
        sr=build_stage_result(pipeline=pipeline,coordination=coordination,stage=stage,input_references=inputs,output_references=out,evidence_summary={"read_back_validated":True},next_stage=next_stage)
        completed=pipeline["completed_stage_results"]+[ _reference(sr,"stage_result_id","stage_result_fingerprint") ]
        status="running"; action=NEXT.get(stage,"requires_human_approval"); pending=next_stage; current=next_stage
        if MODE_STOP[pipeline["requested_mode"]]==stage:
            status="completed_read_only_preparation"; action="requested_mode_complete"; pending=None; current=stage
        elif next_stage=="human_gate":
            cb={k:v for k,v in coordination.items() if k not in {"coordination_fingerprint","coordination_id"}}
            refs=dict(cb.get("stage_artifact_references",{})); refs.update({"repository_admission":_reference(artifacts["repository_admission"],"repository_root_admission_id","fingerprint"),"repository_analysis_closure":_reference(artifacts["repository_analysis_closure"],"repository_analysis_closure_id","fingerprint"),"objective":_reference(artifacts["objective"],"objective_id","objective_fingerprint"),"planning_closure":_reference(artifacts["planning_closure"],"planning_closure_id","fingerprint"),"proposal":_reference(artifacts["engineering_proposal"],"engineering_proposal_id","fingerprint"),"proposal_review_closure":_reference(artifacts["proposal_review_closure"],"proposal_review_closure_id","fingerprint")})
            cb.update({"current_stage":"awaiting_approval","completed_stages":["intake","repository_admission","repository_analysis","objective_definition","planning","proposal_preparation","proposal_review"],"pending_stage":"awaiting_approval","next_governed_action":"requires_human_approval","coordination_status":"active","stage_artifact_references":refs})
            coordination=stable_work_artifact(cb,"coordination_fingerprint","coordination_id","engineering-work-coordination-")
            handoff=create_human_gate_handoff(coordination); handoff.update({"approval_state":"pending","authorization_state":"not_granted","execution_state":"not_started"}); artifacts["human_gate_handoff"]=handoff
            status="awaiting_human_approval"; action="requires_human_approval"; pending="human_approval"; current="awaiting_human_approval"
        return {"pipeline":_updated_pipeline(pipeline,status=status,current=current,completed=completed,pending=pending,action=action,human=status=="awaiting_human_approval"),"coordination":coordination,"artifacts":artifacts,"stage_result":sr}
    except ReadOnlyPipelineError as e:
        sr=build_stage_result(pipeline=pipeline,coordination=coordination,stage=stage,input_references=inputs,output_references=[],stage_status="awaiting_input" if e.code in {"missing_acceptance_criteria","manual_artifact_required"} else "blocked",missing_inputs=[e.code],blocked_reasons=[e.code],next_stage=stage)
        return {"pipeline":_updated_pipeline(pipeline,status="awaiting_input" if sr["stage_status"]=="awaiting_input" else "blocked",current=stage,completed=pipeline["completed_stage_results"],pending=stage,action="requires_acceptance_criteria" if e.code=="missing_acceptance_criteria" else "blocked",missing=[e.code],blocked=[e.code]),"coordination":coordination,"artifacts":artifacts,"stage_result":sr}

def run_read_only_pipeline(req,intake,coordination,pipeline,*,repository_root:str|Path|None=None,artifacts:Mapping[str,Any]|None=None,max_stages:int=7):
    out={"pipeline":pipeline,"coordination":coordination,"artifacts":dict(artifacts or {}),"stage_results":[]}
    for _ in range(max_stages):
        if out["pipeline"]["pipeline_status"] in {"awaiting_input","awaiting_human_approval","completed_read_only_preparation","blocked","failed","invalid"}: break
        n=run_next_read_only_stage(req,intake,out["coordination"],out["pipeline"],repository_root=repository_root,artifacts=out["artifacts"])
        out.update({"pipeline":n["pipeline"],"coordination":n["coordination"],"artifacts":n["artifacts"]})
        if n.get("stage_result"): out["stage_results"].append(n["stage_result"])
    out["journal"]=make_journal(out["coordination"],["read_only_pipeline_created"]+[r["stage"]+"_completed" for r in out["stage_results"]])
    out["checkpoint"]=make_checkpoint(out["coordination"],out["journal"])
    return out

def inspect_read_only_pipeline(coordination:Mapping[str,Any], pipeline:Mapping[str,Any]|None=None, artifacts:Mapping[str,Any]|None=None)->dict[str,Any]:
    if pipeline is None: return {"read_only_pipeline_status":"not_initialized"}
    _verify_stable(pipeline,PIPELINE_SCHEMA,"pipeline_fingerprint","pipeline_id","engineering-read-only-pipeline-")
    artifacts=dict(artifacts or {})
    stages=[r.get("stage") for r in pipeline.get("completed_stage_results",[])]
    timeline=[{"stage":name,"status":status} for name,status in (("Work Request","Completed"),("Work Intake","Completed"),("Repository Admission","Completed" if "repository_admission" in artifacts else "Pending"),("Repository Analysis","Completed" if "repository_analysis_closure" in artifacts else "Pending"),("Session Objectives","Completed" if "objective" in artifacts else "Pending"),("Engineering Planning","Completed" if "planning_closure" in artifacts else "Pending"),("Proposal Preparation","Completed" if "engineering_proposal" in artifacts else "Pending"),("Proposal Review","Completed" if "proposal_review_closure" in artifacts else "Pending"),("Human Approval","Pending" if pipeline.get("human_action_required") else "Not Started"),("Authorization","Not Started"),("Execution","Not Started"))]
    return {"read_only_pipeline_status":pipeline["pipeline_status"],"pipeline_id":pipeline["pipeline_id"],"pipeline_current_stage":pipeline["current_stage"],"pipeline_completed_stages":stages,"latest_stage_result":pipeline.get("completed_stage_results",[])[-1] if pipeline.get("completed_stage_results") else None,"repository_admission_status":artifacts.get("repository_admission",{}).get("status"),"repository_analysis_closure_reference":_reference(artifacts["repository_analysis_closure"],"repository_analysis_closure_id","fingerprint") if "repository_analysis_closure" in artifacts else None,"objective_reference":_reference(artifacts["objective"],"objective_id","objective_fingerprint") if "objective" in artifacts else None,"planning_closure_reference":_reference(artifacts["planning_closure"],"planning_closure_id","fingerprint") if "planning_closure" in artifacts else None,"proposal_reference":_reference(artifacts["engineering_proposal"],"engineering_proposal_id","fingerprint") if "engineering_proposal" in artifacts else None,"proposal_review_closure_reference":_reference(artifacts["proposal_review_closure"],"proposal_review_closure_id","fingerprint") if "proposal_review_closure" in artifacts else None,"human_gate_handoff_reference":_reference(artifacts["human_gate_handoff"],"handoff_id","handoff_fingerprint") if "human_gate_handoff" in artifacts else None,"requested_mode_completion":pipeline["pipeline_status"]=="completed_read_only_preparation","read_only_authority":"not_granted","timeline":timeline,"human_action_required":pipeline.get("human_action_required")}

def resume_read_only_pipeline(coordination,pipeline=None,stage_results:Sequence[Mapping[str,Any]]=(),checkpoint:Mapping[str,Any]|None=None):
    if pipeline is None: return {"decision":"requires_repository_admission","read_only_pipeline_status":"not_initialized","will_approve":False,"will_authorize":False,"will_execute":False,"will_mutate_repository":False,"will_complete_session":False}
    try: _verify_stable(pipeline,PIPELINE_SCHEMA,"pipeline_fingerprint","pipeline_id","engineering-read-only-pipeline-")
    except ReadOnlyPipelineError: return {"decision":"invalid","will_approve":False,"will_authorize":False,"will_execute":False,"will_mutate_repository":False,"will_complete_session":False}
    decision=pipeline.get("next_governed_action")
    return {"decision":decision,"next_governed_action":decision,"pipeline_status":pipeline.get("pipeline_status"),"will_approve":False,"will_authorize":False,"will_execute":False,"will_mutate_repository":False,"will_complete_session":False}

def verify_read_only_pipeline(pipeline, stage_results:Sequence[Mapping[str,Any]]=(), checkpoint:Mapping[str,Any]|None=None):
    try:
        _verify_stable(pipeline,PIPELINE_SCHEMA,"pipeline_fingerprint","pipeline_id","engineering-read-only-pipeline-")
        for r in stage_results: _verify_stable(r,STAGE_SCHEMA,"stage_result_fingerprint","stage_result_id","engineering-read-only-stage-")
        return {"valid":True,"pipeline_status":pipeline.get("pipeline_status"),"stage_result_count":len(stage_results)}
    except ReadOnlyPipelineError as e: return {"valid":False,"error":e.code}
