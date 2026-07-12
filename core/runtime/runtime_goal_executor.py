from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any,Mapping

from core.runtime.runtime_controlled_tool_adapter import CONTRACT as ADAPTER_CONTRACT,MAX_CANDIDATE_BYTES,MAX_CANDIDATE_FILES,create_tool_request,execute_controlled_tool
from core.runtime.runtime_candidate_authoring_engine import author_candidate,create_authoring_request
from core.runtime.runtime_operator_session import fingerprint,time_text

CONTRACT="zero.runtime.goal_executor.v1";REQUEST_CONTRACT="zero.runtime.goal_execution_request.v1";RESULT_CONTRACT="zero.runtime.goal_execution_result.v1"
SUPPORTED_GOALS={"inspect","document","modify","validate"}
def _mapping(v:Any)->dict[str,Any]:return deepcopy(dict(v)) if isinstance(v,Mapping) else {}
def create_goal_execution_request(goal:Mapping[str,Any],session:Mapping[str,Any],*,operator_context:Mapping[str,Any],now:Any=None)->dict[str,Any]:
    g=_mapping(goal);s=_mapping(session);context=_mapping(operator_context);seed={"goal_id":g.get("goal_id"),"session_id":s.get("session_id"),"goal_fingerprint":g.get("goal_fingerprint"),"session_fingerprint":s.get("session_fingerprint"),"operator_context":context}
    value={"contract":REQUEST_CONTRACT,"execution_request_id":f"goal-execution-{fingerprint(seed)[:20]}","goal_id":g.get("goal_id"),"mission_id":g.get("mission_id"),"session_id":s.get("session_id"),"goal_type":g.get("goal_type"),"approved_scope":deepcopy(g.get("target_scope")or[]),"excluded_scope":deepcopy(g.get("excluded_scope")or[]),"acceptance_criteria":deepcopy(g.get("acceptance_criteria")or[]),"validation_requirements":deepcopy(g.get("validation_requirements")or[]),"operator_context":context,"created_at":time_text(now),"goal_fingerprint":g.get("goal_fingerprint"),"session_fingerprint":s.get("session_fingerprint")}
    value["execution_request_fingerprint"]=fingerprint(value);return value
def execute_goal(request:Mapping[str,Any],*,workspace_root:Any,artifact_root:Any,now:Any=None)->dict[str,Any]:
    req=_mapping(request);reasons=[]
    if req.get("contract")!=REQUEST_CONTRACT:reasons.append("invalid_goal_execution_request_contract")
    if req.get("execution_request_fingerprint")!=fingerprint({k:v for k,v in req.items() if k!="execution_request_fingerprint"}):reasons.append("goal_execution_request_fingerprint_mismatch")
    if req.get("goal_type") not in SUPPORTED_GOALS:reasons.append("unsupported_goal_type")
    scope=list(req.get("approved_scope")or[]);context=_mapping(req.get("operator_context"))
    if not scope:reasons.append("approved_scope_required")
    if len(scope)>MAX_CANDIDATE_FILES:reasons.append("candidate_file_count_limit_exceeded")
    if any(key in context for key in ("command","shell","argv","callable","subprocess")):reasons.append("executable_context_forbidden")
    if reasons:return _result(req,"blocked",reasons,[],[],now)
    candidates=[];validations=[];tools=[];inspections=[]
    for index,relative in enumerate(scope):
        operation=None;authoring_request=None;authored=None
        inspect=create_tool_request("inspect_file",relative,request_id=f"{req['execution_request_id']}:inspect:{index}",source_goal_id=req["goal_id"],source_session_id=req["session_id"],execution_request_fingerprint=req["execution_request_fingerprint"],now=now)
        inspected=execute_controlled_tool(inspect,workspace_root=workspace_root,artifact_root=artifact_root,approved_scope=scope,now=now);tools.append(inspected)
        if inspected["status"]!="completed":return _result(req,"blocked",inspected["reasons"],candidates,validations,now,tools)
        inspections.append(inspected["result"])
        original=Path(workspace_root,relative).read_text(encoding="utf-8-sig")
        if req["goal_type"] in {"document","modify"}:
            replacement=context.get("replacement_text");append=context.get("append_text")
            instruction=_mapping(context.get("authoring_instruction")) or deepcopy(context)
            instruction["target_files"]=[relative]
            if not instruction.get("authoring_strategy"):
                if append is not None:instruction["authoring_strategy"]="append_text"
                elif "exact_text" in instruction:instruction["authoring_strategy"]="replace_exact_text"
            if instruction.get("authoring_strategy"):
                goal={"goal_id":req.get("goal_id"),"mission_id":req.get("mission_id"),"goal_type":req.get("goal_type"),"target_scope":scope,"excluded_scope":req.get("excluded_scope")or[],"acceptance_criteria":req.get("acceptance_criteria")or["Apply the exact controlled authoring instruction"],"validation_requirements":req.get("validation_requirements")or(["Python syntax must parse"] if relative.lower().endswith(".py") else ["Candidate content must be text"])}
                session={"session_id":req.get("session_id")}
                authoring_request=create_authoring_request(goal=goal,session=session,authoring_instruction=instruction,repository_context_references=inspections,inspect_evidence_references=inspections,now=now)
                authored=author_candidate(authoring_request,workspace_root=workspace_root,now=now)
                if authored["status"]!="candidate_ready":return _result(req,"clarification_required",authored.get("warnings")or[],candidates,validations,now,tools,authoring_request,authored)
                operation=next((item for item in authored["candidate_operations"] if item["relative_path"]==relative),None)
                if operation is None:return _result(req,"clarification_required",["candidate_operation_missing"],candidates,validations,now,tools,authoring_request,authored)
                content=operation["content"]
            else:
                if replacement is None:return _result(req,"clarification_required",["candidate_text_instruction_required"],candidates,validations,now,tools)
                content=str(replacement);authoring_request=None;authored=None
        else:content=original
        write=create_tool_request("write_text_candidate",relative,request_id=f"{req['execution_request_id']}:candidate:{index}",source_goal_id=req["goal_id"],source_session_id=req["session_id"],execution_request_fingerprint=req["execution_request_fingerprint"],content=content,operation=(operation.get("operation") if req["goal_type"] in {"document","modify"} and 'operation' in locals() and operation else "replace"),now=now)
        written=execute_controlled_tool(write,workspace_root=workspace_root,artifact_root=artifact_root,approved_scope=scope,now=now);tools.append(written)
        if written["status"]!="completed":return _result(req,"blocked",written["reasons"],candidates,validations,now,tools)
        candidate=written["result"];candidates.append(candidate)
        if sum(int(item.get("size_bytes")or 0) for item in candidates)>MAX_CANDIDATE_BYTES:return _result(req,"blocked",["candidate_total_bytes_limit_exceeded"],candidates,validations,now,tools)
        if relative.lower().endswith(".py") or req["goal_type"]=="validate":
            validate=create_tool_request("validate_python_source" if relative.lower().endswith(".py") else "validate_text_contains",relative,request_id=f"{req['execution_request_id']}:validate:{index}",source_goal_id=req["goal_id"],source_session_id=req["session_id"],execution_request_fingerprint=req["execution_request_fingerprint"],content=content,expected_text=context.get("expected_text")or content[:1],now=now)
            checked=execute_controlled_tool(validate,workspace_root=workspace_root,artifact_root=artifact_root,approved_scope=scope,now=now);tools.append(checked)
            if checked["status"]!="completed":return _result(req,"blocked",checked["reasons"],candidates,validations,now,tools)
            validations.append(checked["result"])
    status="validation_failed" if any(v.get("passed")is False for v in validations) else "candidate_ready"
    return _result(req,status,[],candidates,validations,now,tools,locals().get("authoring_request"),locals().get("authored"))
def _result(req,status,reasons,candidates,validations,now,tools=None,authoring_request=None,authoring_output=None):
    value={"contract":RESULT_CONTRACT,"executor_contract":CONTRACT,"execution_request_id":req.get("execution_request_id"),"execution_request_fingerprint":req.get("execution_request_fingerprint"),"goal_id":req.get("goal_id"),"session_id":req.get("session_id"),"execution_status":status,"candidate_files":deepcopy(candidates),"validation_evidence":deepcopy(validations),"tool_results":deepcopy(tools or[]),"authoring_request":deepcopy(authoring_request),"authoring_output":deepcopy(authoring_output),"reasons":sorted(set(reasons)),"generated_at":time_text(now),"workspace_mutated":False,"session_created":False,"queue_mutated":False,"transaction_invoked":False,"commit_performed":False,"tool_adapter_contract":ADAPTER_CONTRACT}
    value["execution_result_fingerprint"]=fingerprint(value);return value
__all__=["CONTRACT","REQUEST_CONTRACT","RESULT_CONTRACT","SUPPORTED_GOALS","create_goal_execution_request","execute_goal"]
