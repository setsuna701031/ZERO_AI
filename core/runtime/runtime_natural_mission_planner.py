from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json, os, stat
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

from core.runtime.runtime_goal_graph import GOAL_TYPES, MAX_DEPENDENCIES, build_goal_graph
from core.runtime.runtime_operator_session import fingerprint, parse_time, root_identity, time_text

NATURAL_INPUT_CONTRACT="zero.runtime.natural_mission_input.v1"
PLANNING_REQUEST_CONTRACT="zero.runtime.mission_planning_request.v1"
PLANNER_OUTPUT_CONTRACT="zero.runtime.mission_planner_output.v1"
MAX_PLANNER_GOALS=50; MAX_CONTEXT_FILES=100; MAX_CONTEXT_FILE_BYTES=65536; MAX_CONTEXT_BYTES=524288; MAX_SUMMARY_LENGTH=2000
FORBIDDEN={"candidate_content","patch_text","diff","shell_command","command","commands","argv","script","callable","import_path","executable_payload","test_command","shell"}
KNOWN_CAPABILITIES={"inspect","modify","validate","document","read_repository_context"}

def _mapping(v:Any)->dict[str,Any]:return deepcopy(dict(v)) if isinstance(v,Mapping) else {}
def _unsigned(v:Mapping[str,Any],field:str)->dict[str,Any]:r=_mapping(v);r.pop(field,None);return r
def _safe_relative(v:Any)->str:
    text=str(v or "").replace("\\","/").strip(); p=PurePosixPath(text)
    if not text or p.is_absolute() or ":" in text or any(x in {"",".",".."} for x in p.parts):raise ValueError("unsafe_scope_path")
    return p.as_posix()
def _overlap(a:str,b:str)->bool:return a==b or a.startswith(b+"/") or b.startswith(a+"/")
def _unsafe(path:Path)->bool:
    try:return path.is_symlink() or bool(getattr(path.lstat(),"st_file_attributes",0)&getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0x400))
    except OSError:return False

def create_natural_mission_input(mission_text:str,*,operator_id:str,target_root:Any,workspace_root:Any,requested_scope:list[str]|None=None,excluded_scope:list[str]|None=None,constraints:list[str]|None=None,acceptance_hints:list[str]|None=None,validation_hints:list[str]|None=None,priority:int=0,max_goals:int=20,allow_replanning:bool=True,notes:Any=None,now:Any=None,expires_at:Any=None)->dict[str,Any]:
    text=str(mission_text or "").strip(); operator=str(operator_id or "").strip()
    if not text:raise ValueError("empty_mission_text")
    if not operator:raise ValueError("operator_id_required")
    if isinstance(max_goals,bool) or not 1<=int(max_goals)<=MAX_PLANNER_GOALS:raise ValueError("invalid_max_goals")
    included=[_safe_relative(x) for x in requested_scope or []];excluded=[_safe_relative(x) for x in excluded_scope or []]
    if any(_overlap(a,b) for a in included for b in excluded):raise ValueError("scope_conflict")
    at=time_text(now); expiry=time_text(expires_at or(parse_time(at)+timedelta(days=7)))
    if parse_time(expiry)<=parse_time(at):raise ValueError("natural_mission_expired")
    seed={"mission_text":text,"operator_id":operator,"submitted_at":at,"target":root_identity(target_root),"workspace":root_identity(workspace_root),"requested_scope":included,"excluded_scope":excluded}
    value={"contract":NATURAL_INPUT_CONTRACT,"request_id":f"natural-mission-{fingerprint(seed)[:20]}","mission_text":text,"operator_id":operator,"submitted_at":at,"expires_at":expiry,"target_root_identity":seed["target"],"workspace_root_identity":seed["workspace"],"requested_scope":included,"excluded_scope":excluded,"constraints":deepcopy(constraints or []),"acceptance_hints":deepcopy(acceptance_hints or []),"validation_hints":deepcopy(validation_hints or []),"priority":int(priority),"max_goals":int(max_goals),"planning_mode":"operator_confirmed","allow_replanning":bool(allow_replanning),"notes":notes}
    value["natural_input_fingerprint"]=fingerprint(value);return value

def validate_natural_mission_input(value:Mapping[str,Any],*,target_root:Any=None,workspace_root:Any=None,now:Any=None)->list[str]:
    v=_mapping(value);r=[]
    if v.get("contract")!=NATURAL_INPUT_CONTRACT:r.append("invalid_natural_input_contract")
    if not str(v.get("mission_text")or"").strip():r.append("empty_mission_text")
    if not str(v.get("operator_id")or"").strip():r.append("operator_id_required")
    if FORBIDDEN.intersection(v):r.append("executable_fields_forbidden")
    try:
        included=[_safe_relative(x) for x in v.get("requested_scope",[])];excluded=[_safe_relative(x) for x in v.get("excluded_scope",[])]
        if any(_overlap(a,b) for a in included for b in excluded):r.append("scope_conflict")
        if parse_time(now or datetime.now(timezone.utc))>=parse_time(v.get("expires_at")):r.append("natural_mission_expired")
        if target_root is not None and root_identity(target_root)!=v.get("target_root_identity"):r.append("target_root_mismatch")
        if workspace_root is not None and root_identity(workspace_root)!=v.get("workspace_root_identity"):r.append("workspace_root_mismatch")
    except (ValueError,TypeError,OSError):r.append("invalid_natural_input")
    if not 1<=int(v.get("max_goals",0))<=MAX_PLANNER_GOALS:r.append("invalid_max_goals")
    claimed=v.get("natural_input_fingerprint");unsigned=_mapping(v);unsigned.pop("natural_input_fingerprint",None)
    if claimed and claimed!=fingerprint(unsigned):r.append("natural_input_fingerprint_mismatch")
    return sorted(set(r))

def collect_repository_context(target_root:Any,scopes:list[str],*,max_files:int=MAX_CONTEXT_FILES,max_file_bytes:int=MAX_CONTEXT_FILE_BYTES,max_total_bytes:int=MAX_CONTEXT_BYTES)->dict[str,Any]:
    root=Path(target_root).resolve(strict=True);files=[];total=0
    for scope in scopes:
        path=(root/_safe_relative(scope)).resolve(strict=False)
        if not path.is_relative_to(root) or _unsafe(path):raise ValueError("unsafe_repository_context")
        candidates=[path] if path.is_file() else sorted((p for p in path.rglob("*") if p.is_file()),key=lambda p:p.as_posix()) if path.exists() else []
        for item in candidates:
            if len(files)>=max_files:break
            if _unsafe(item) or not item.resolve().is_relative_to(root):raise ValueError("unsafe_repository_context")
            size=item.stat().st_size
            if size>max_file_bytes or total+size>max_total_bytes:continue
            raw=item.read_bytes()
            if b"\x00" in raw:continue
            try:text=raw.decode("utf-8-sig")
            except UnicodeError:continue
            total+=size;files.append({"relative_path":item.relative_to(root).as_posix(),"file_type":item.suffix.lower(),"exists":True,"size_bytes":size,"summary":text[:MAX_SUMMARY_LENGTH],"content_fingerprint":fingerprint(text)})
    return {"files":files,"file_count":len(files),"total_bytes":total,"context_fingerprint":fingerprint(files)}

def create_planning_request(natural_input:Mapping[str,Any],*,repository_context:Mapping[str,Any]|None=None,memory_evidence:Any=None,now:Any=None)->dict[str,Any]:
    source=_mapping(natural_input);reasons=validate_natural_mission_input(source,now=now)
    if reasons:raise ValueError(";".join(reasons))
    at=time_text(now);memory=[]
    for item in list(memory_evidence or [])[:20]:
        m=_mapping(item);memory.append({"reference":m.get("reference")or m.get("activity_id"),"fingerprint":m.get("fingerprint")or fingerprint(m),"similarity":m.get("similarity"),"summary":str(m.get("summary")or m.get("outcome")or"")[:500]})
    context=_mapping(repository_context)
    seed={"request":source["request_id"],"revision":1,"generated_at":at}
    value={"contract":PLANNING_REQUEST_CONTRACT,"planning_request_id":f"planning-request-{fingerprint(seed)[:20]}","natural_mission_request_id":source["request_id"],"mission_text":source["mission_text"],"normalized_intent_summary":" ".join(source["mission_text"].split()),"target_root_identity":source["target_root_identity"],"workspace_root_identity":source["workspace_root_identity"],"requested_scope":deepcopy(source["requested_scope"]),"excluded_scope":deepcopy(source["excluded_scope"]),"available_capability_summary":sorted(KNOWN_CAPABILITIES),"runtime_safety_boundaries":["operator_plan_confirmation","session_operator_gates","no_direct_execution","no_scope_expansion"],"acceptance_hints":deepcopy(source["acceptance_hints"]),"validation_hints":deepcopy(source["validation_hints"]),"historical_evidence_summary":memory,"known_repository_context_references":[{k:f.get(k) for k in ("relative_path","content_fingerprint","exists","file_type")} for f in context.get("files",[])],"maximum_goals":source["max_goals"],"maximum_dependencies":MAX_DEPENDENCIES,"planning_policy":"conservative_operator_confirmed","generated_at":at,"expires_at":source["expires_at"],"audit_record":{"event_type":"mission_planning_request_created","created_at":at}}
    value["planning_request_fingerprint"]=fingerprint(value);return value

def deterministic_rule_planner(request:Mapping[str,Any])->dict[str,Any]:
    req=_mapping(request);text=str(req.get("mission_text")or"");lower=text.casefold();scope=deepcopy(req.get("requested_scope")or[]);excluded=deepcopy(req.get("excluded_scope")or[])
    inspect=any(x in lower for x in ("inspect","check","review","檢查","查看","盤點"));modify=any(x in lower for x in ("update","modify","fix","補","更新","修改","修正"));document=any(x in lower for x in ("readme","doc","文件","說明"));validate=any(x in lower for x in ("test","validate","驗證","測試","最後"))
    if not any((inspect,modify,document,validate)):
        return _planner_output(req,[],"clarification_required",["請明確指出要檢查、修改、文件化或驗證的工作。"])
    specs=[]
    def add(kind,title,description):
        pid=f"planned-goal-{len(specs)+1}";deps=[specs[-1]["provisional_goal_id"]] if specs else []
        criteria=list(req.get("acceptance_hints")or[] ) or [f"{title} completed within approved scope"]
        validation=list(req.get("validation_hints")or[]) or (["Review focused validation evidence"] if kind=="validate" else ["Verify goal acceptance criteria"])
        specs.append({"provisional_goal_id":pid,"title":title,"description":description,"goal_type":kind,"priority":0,"depends_on":deps,"target_scope":scope,"excluded_scope":excluded,"required_capabilities":[kind],"acceptance_criteria":criteria,"validation_requirements":validation,"operator_confirmation_required":True,"expected_artifacts":[],"failure_policy":"block_dependents","max_attempts":3,"rationale":"Conservative decomposition of explicit mission intent","uncertainty":[] if scope else ["target scope was not explicitly provided"],"evidence_requirements":["session final evidence"]})
    if inspect or modify or document:add("inspect","Inspect approved scope","Inspect existing state without mutation")
    if modify:add("document" if document else "modify","Update approved scope","Apply the operator-approved change through the existing Session runtime")
    elif document:add("document","Document approved scope","Update documentation only within approved scope")
    if validate:add("validate","Validate mission outcome","Perform focused validation through the existing controlled runtime")
    return _planner_output(req,specs,"planned",[])

def _planner_output(req:Mapping[str,Any],goals:list[dict[str,Any]],status:str,reasons:list[str],provider:str="deterministic_rule")->dict[str,Any]:
    at=req.get("generated_at");order=[g["provisional_goal_id"] for g in goals]
    value={"contract":PLANNER_OUTPUT_CONTRACT,"planner_output_id":"","planning_request_id":req.get("planning_request_id"),"planner_provider":provider,"planner_version":"1","plan_status":status,"mission_title":str(req.get("normalized_intent_summary")or"Mission")[:160],"mission_description":req.get("mission_text"),"assumptions":[],"clarifications":reasons if status=="clarification_required" else [],"scope_summary":{"included":deepcopy(req.get("requested_scope")or[]),"excluded":deepcopy(req.get("excluded_scope")or[]),"unknown":[] if req.get("requested_scope") else ["target scope not explicitly provided"]},"risk_summary":["All execution remains behind Mission and Session operator gates"],"operator_boundaries":["Mission plan confirmation required","Session approvals remain required"],"goals":goals,"goal_order":order,"dependency_edges":[{"from":d,"to":g["provisional_goal_id"]} for g in goals for d in g["depends_on"]],"mission_acceptance_criteria":deepcopy(req.get("acceptance_hints")or["All confirmed goals satisfy their acceptance criteria"]),"mission_validation_requirements":deepcopy(req.get("validation_hints")or["Review final Mission evidence"]),"estimated_complexity":"low" if len(goals)<=3 else "medium","replanning_policy":{"allowed":True,"confirmation_required":True},"reasons":reasons,"generated_at":at,"expires_at":req.get("expires_at"),"audit_record":{"event_type":"mission_planner_output_created","created_at":at}}
    value["planner_output_id"]=f"planner-output-{fingerprint(value)[:20]}";value["planner_output_fingerprint"]=fingerprint(value);return value

def validate_planner_output(output:Mapping[str,Any],request:Mapping[str,Any],*,now:Any=None)->list[str]:
    v=_mapping(output);req=_mapping(request);r=[]
    if v.get("contract")!=PLANNER_OUTPUT_CONTRACT:r.append("invalid_planner_output_contract")
    if v.get("planning_request_id")!=req.get("planning_request_id"):r.append("planning_request_mismatch")
    if v.get("plan_status") not in {"planned","clarification_required","blocked","invalid"}:r.append("invalid_plan_status")
    if v.get("planner_output_fingerprint")!=fingerprint(_unsigned(v,"planner_output_fingerprint")):r.append("planner_output_fingerprint_mismatch")
    try:
        if parse_time(now or req.get("generated_at"))>=parse_time(v.get("expires_at")):r.append("planner_output_expired")
    except (ValueError,TypeError):r.append("invalid_planner_expiration")
    goals=list(v.get("goals")or[])
    if len(goals)>int(req.get("maximum_goals",0)):r.append("planner_goal_limit_exceeded")
    included=list(req.get("requested_scope")or[]);excluded=list(req.get("excluded_scope")or[])
    converted=[]
    for g in goals:
        item=_mapping(g)
        if FORBIDDEN.intersection(item):r.append("executable_planner_goal_forbidden")
        if item.get("goal_type") not in GOAL_TYPES:r.append("invalid_goal_type")
        if not item.get("acceptance_criteria"):r.append("missing_acceptance_criteria")
        if not item.get("validation_requirements"):r.append("missing_validation_requirements")
        if any(c not in KNOWN_CAPABILITIES for c in item.get("required_capabilities",[])):r.append("unknown_capability")
        try:scopes=[_safe_relative(x) for x in item.get("target_scope",[])]
        except ValueError:scopes=[];r.append("unsafe_goal_scope")
        if included and any(not any(_overlap(s,i) and (s==i or s.startswith(i+"/")) for i in included) for s in scopes):r.append("scope_expansion")
        if any(_overlap(s,e) for s in scopes for e in excluded):r.append("excluded_scope_violation")
        converted.append({"goal_id":item.get("provisional_goal_id"),"goal_title":item.get("title"),"goal_description":item.get("description"),"goal_type":item.get("goal_type"),"goal_status":"pending","priority":item.get("priority",0),"depends_on":item.get("depends_on",[]),"target_scope":item.get("target_scope",[]),"required_capabilities":item.get("required_capabilities",[]),"acceptance_criteria":item.get("acceptance_criteria",[]),"validation_requirements":item.get("validation_requirements",[])})
    if v.get("plan_status")=="planned":
        if not v.get("risk_summary"):r.append("missing_risk_summary")
        if not v.get("operator_boundaries"):r.append("missing_operator_boundaries")
        try:
            built=build_goal_graph(converted,mission_id="planner-validation")
            if built["goal_order"]!=v.get("goal_order"):r.append("planner_goal_order_mismatch")
        except ValueError as exc:r.append(str(exc))
    return sorted(set(r))

def plan_natural_mission(natural_mission_input:Mapping[str,Any],*,target_root:Any,workspace_root:Any,repository_context:Mapping[str,Any]|None=None,memory_evidence:Any=None,planner_provider:Callable[[Mapping[str,Any]],Mapping[str,Any]]|None=None,now:Any=None,runtime_config:Mapping[str,Any]|None=None)->dict[str,Any]:
    source=_mapping(natural_mission_input);reasons=validate_natural_mission_input(source,target_root=target_root,workspace_root=workspace_root,now=now)
    if reasons:raise ValueError(";".join(reasons))
    context=_mapping(repository_context) if repository_context is not None else collect_repository_context(target_root,source.get("requested_scope",[]))
    request=create_planning_request(source,repository_context=context,memory_evidence=memory_evidence,now=now)
    output=_mapping(planner_provider(deepcopy(request))) if planner_provider else deterministic_rule_planner(request)
    reasons=validate_planner_output(output,request,now=now)
    if reasons:raise ValueError(";".join(reasons))
    return {"natural_mission_input":source,"planning_request":request,"planner_output":output,"repository_context_summary":{"file_count":context.get("file_count",0),"total_bytes":context.get("total_bytes",0),"context_fingerprint":context.get("context_fingerprint")}}

def planner_output_to_goal_plan(output:Mapping[str,Any])->list[dict[str,Any]]:
    return [{"goal_id":g["provisional_goal_id"],"goal_title":g["title"],"goal_description":g["description"],"goal_type":g["goal_type"],"priority":g.get("priority",0),"depends_on":deepcopy(g.get("depends_on",[])),"target_scope":deepcopy(g.get("target_scope",[])),"required_capabilities":deepcopy(g.get("required_capabilities",[])),"acceptance_criteria":deepcopy(g.get("acceptance_criteria",[])),"validation_requirements":deepcopy(g.get("validation_requirements",[])),"operator_confirmation_required":True,"max_attempts":g.get("max_attempts",3)} for g in output.get("goals",[])]

def create_mission_from_planner_output(natural_mission_input:Mapping[str,Any],planner_output:Mapping[str,Any],*,planning_request:Mapping[str,Any],target_root:Any,workspace_root:Any,mission_path:Any=None,scheduler_state_path:Any=None,now:Any=None,runtime_config:Mapping[str,Any]|None=None,planner_output_path:Any=None,planning_request_path:Any=None)->dict[str,Any]:
    reasons=validate_natural_mission_input(natural_mission_input,target_root=target_root,workspace_root=workspace_root,now=now)+validate_planner_output(planner_output,planning_request,now=now)
    if reasons:raise ValueError(";".join(sorted(set(reasons))))
    if planner_output.get("plan_status")!="planned":raise ValueError("planner_output_not_plannable")
    from core.runtime.runtime_mission_orchestrator import create_mission
    mission=create_mission({"mission_title":planner_output.get("mission_title"),"mission_description":planner_output.get("mission_description"),"natural_request_id":natural_mission_input.get("request_id")},goal_plan=planner_output_to_goal_plan(planner_output),target_root=target_root,workspace_root=workspace_root,mission_path=mission_path,scheduler_state_path=scheduler_state_path,now=now,runtime_config=runtime_config)
    mission["natural_mission_request_reference"]={"request_id":natural_mission_input["request_id"],"fingerprint":natural_mission_input.get("natural_input_fingerprint")};mission["planning_request_reference"]={"planning_request_id":planning_request["planning_request_id"],"fingerprint":planning_request["planning_request_fingerprint"],"path":str(planning_request_path) if planning_request_path else None};mission["planner_output_reference"]={"planner_output_id":planner_output["planner_output_id"],"fingerprint":planner_output["planner_output_fingerprint"],"path":str(planner_output_path) if planner_output_path else None}
    mission["planning_revision"]=1;mission["planning_status"]="waiting_for_plan_confirmation";mission["clarification_required"]=False;mission["planner_evidence_references"]=deepcopy(planning_request.get("historical_evidence_summary",[]));mission["planner_output_scope"]=deepcopy(planner_output.get("scope_summary",{}).get("included",[]));mission["last_planning_checkpoint"]={"at":time_text(now),"planning_request_id":planning_request["planning_request_id"],"planner_output_id":planner_output["planner_output_id"]}
    mission["planner_output_summary"]={"goal_count":len(planner_output.get("goals",[])),"risk_count":len(planner_output.get("risk_summary",[])),"unknown_scope_count":len(_mapping(planner_output.get("scope_summary")).get("unknown",[])),"operator_boundaries_count":len(planner_output.get("operator_boundaries",[])),"included_scope":deepcopy(_mapping(planner_output.get("scope_summary")).get("included",[])),"excluded_scope":deepcopy(_mapping(planner_output.get("scope_summary")).get("excluded",[])),"risk_summary":deepcopy(planner_output.get("risk_summary",[])),"operator_boundaries":deepcopy(planner_output.get("operator_boundaries",[]))}
    from core.runtime.runtime_mission_model import save_mission,seal_mission
    mission=seal_mission(mission);return save_mission(mission,mission_path) if mission_path else mission

def save_planner_artifact(value:Mapping[str,Any],path:Any)->dict[str,Any]:
    dest=Path(path)
    if dest.exists() and _unsafe(dest):raise ValueError("unsafe_planner_artifact_path")
    dest.parent.mkdir(parents=True,exist_ok=True)
    if _unsafe(dest.parent):raise ValueError("unsafe_planner_artifact_directory")
    tmp=dest.with_name(f".{dest.name}.tmp")
    with tmp.open("w",encoding="utf-8",newline="\n") as h:h.write(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+"\n");h.flush();os.fsync(h.fileno())
    os.replace(tmp,dest);return _mapping(value)
def load_planner_artifact(path:Any)->dict[str,Any]:
    src=Path(path)
    if _unsafe(src):raise ValueError("unsafe_planner_artifact_path")
    try:return json.loads(src.read_text(encoding="utf-8-sig"))
    except (OSError,UnicodeError,json.JSONDecodeError) as exc:raise ValueError("invalid_planner_artifact_json") from exc

__all__=["KNOWN_CAPABILITIES","MAX_CONTEXT_BYTES","MAX_CONTEXT_FILE_BYTES","MAX_CONTEXT_FILES","MAX_PLANNER_GOALS","NATURAL_INPUT_CONTRACT","PLANNER_OUTPUT_CONTRACT","PLANNING_REQUEST_CONTRACT","collect_repository_context","create_mission_from_planner_output","create_natural_mission_input","create_planning_request","deterministic_rule_planner","load_planner_artifact","plan_natural_mission","planner_output_to_goal_plan","save_planner_artifact","validate_natural_mission_input","validate_planner_output"]
