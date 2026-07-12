from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json, os, stat
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from core.runtime.runtime_operator_session import fingerprint, root_identity, time_text

CONTRACT="zero.runtime.controlled_tool_adapter.v1"
REQUEST_CONTRACT="zero.runtime.controlled_tool_request.v1"
RESULT_CONTRACT="zero.runtime.controlled_tool_result.v1"
TOOLS={"inspect_file","write_text_candidate","validate_python_source","validate_text_contains"}
MAX_FILE_BYTES=262144;MAX_CANDIDATE_FILES=20;MAX_CANDIDATE_BYTES=1048576;MAX_PREVIEW=4096

def _mapping(v:Any)->dict[str,Any]:return deepcopy(dict(v)) if isinstance(v,Mapping) else {}
def _safe_relative(v:Any)->str:
    text=str(v or "").replace("\\","/").strip();p=PurePosixPath(text)
    if not text or p.is_absolute() or ":" in text or any(x in {"",".",".."} for x in p.parts):raise ValueError("unsafe_relative_path")
    return p.as_posix()
def _unsafe(path:Path)->bool:
    try:return path.is_symlink() or bool(getattr(path.lstat(),"st_file_attributes",0)&getattr(stat,"FILE_ATTRIBUTE_REPARSE_POINT",0x400))
    except OSError:return False
def _resolve(root:Path,relative:Any,*,must_exist:bool)->Path:
    rel=_safe_relative(relative);candidate=(root/rel).resolve(strict=False)
    if not candidate.is_relative_to(root):raise ValueError("path_escape")
    cursor=root
    for part in PurePosixPath(rel).parts:
        cursor=cursor/part
        if cursor.exists() and _unsafe(cursor):raise ValueError("symlink_or_reparse_forbidden")
    if must_exist and not candidate.is_file():raise ValueError("file_not_found")
    return candidate
def _allowed(relative:str,scope:list[str])->bool:return any(relative==item or relative.startswith(item.rstrip("/")+"/") for item in scope)
def _base(request:Mapping[str,Any],status:str,reasons:list[str],now:Any)->dict[str,Any]:
    value={"contract":RESULT_CONTRACT,"adapter_contract":CONTRACT,"request_id":request.get("request_id"),"tool":request.get("tool"),"status":status,"reasons":sorted(set(reasons)),"generated_at":time_text(now),"result":{},"workspace_mutated":False,"transaction_invoked":False}
    value["result_fingerprint"]=fingerprint(value);return value

def execute_controlled_tool(request:Mapping[str,Any],*,workspace_root:Any,artifact_root:Any,approved_scope:list[str],now:Any=None)->dict[str,Any]:
    source=_mapping(request);root=Path(workspace_root).resolve(strict=True);artifacts=Path(artifact_root).resolve(strict=False)
    if source.get("contract")!=REQUEST_CONTRACT:return _base(source,"blocked",["invalid_tool_request_contract"],now)
    if source.get("request_fingerprint")!=fingerprint({k:v for k,v in source.items() if k!="request_fingerprint"}):return _base(source,"blocked",["tool_request_fingerprint_mismatch"],now)
    tool=source.get("tool")
    if tool not in TOOLS:return _base(source,"blocked",["unsupported_tool"],now)
    try:
        relative=_safe_relative(source.get("relative_path"));scope=[_safe_relative(x) for x in approved_scope]
        if not _allowed(relative,scope):raise ValueError("scope_mismatch")
        path=_resolve(root,relative,must_exist=tool!="write_text_candidate" or source.get("operation","replace")!="create")
        if tool=="inspect_file":
            raw=path.read_bytes()
            if len(raw)>int(source.get("max_bytes")or MAX_FILE_BYTES) or len(raw)>MAX_FILE_BYTES:raise ValueError("file_bytes_limit_exceeded")
            if b"\0" in raw:raise ValueError("binary_file_forbidden")
            try:text=raw.decode("utf-8-sig")
            except UnicodeError:raise ValueError("non_utf8_file_forbidden")
            result={"relative_path":relative,"sha256":sha256(raw).hexdigest(),"size_bytes":len(raw),"preview":text[:MAX_PREVIEW],"reference":f"workspace:{relative}","workspace_root_identity":root_identity(root)}
        elif tool=="write_text_candidate":
            content=source.get("content")
            if not isinstance(content,str):raise ValueError("candidate_text_required")
            raw=content.encode("utf-8")
            if len(raw)>MAX_FILE_BYTES:raise ValueError("candidate_file_bytes_limit_exceeded")
            if artifacts==root or artifacts.is_relative_to(root):raise ValueError("artifact_root_inside_workspace")
            artifacts.mkdir(parents=True,exist_ok=True)
            if _unsafe(artifacts):raise ValueError("unsafe_artifact_root")
            expected=path.read_bytes() if path.exists() else None;candidate_id=f"candidate-{fingerprint({'request':source['request_id'],'path':relative,'content':sha256(raw).hexdigest()})[:20]}"
            destination=artifacts/f"{candidate_id}.txt"
            if _unsafe(destination):raise ValueError("unsafe_candidate_path")
            temporary=destination.with_name(f".{destination.name}.tmp")
            with temporary.open("wb") as handle:handle.write(raw);handle.flush();os.fsync(handle.fileno())
            os.replace(temporary,destination)
            result={"candidate_id":candidate_id,"relative_path":relative,"operation":source.get("operation")or("replace" if expected is not None else "create"),"expected_original_sha256":sha256(expected).hexdigest() if expected is not None else None,"expected_original_size":len(expected) if expected is not None else None,"candidate_sha256":sha256(raw).hexdigest(),"candidate_reference":str(destination.resolve()),"size_bytes":len(raw),"candidate_content_encoding":"utf-8","source_goal_id":source.get("source_goal_id"),"source_session_id":source.get("source_session_id"),"tool_adapter_contract":CONTRACT,"execution_request_fingerprint":source.get("execution_request_fingerprint")}
        elif tool=="validate_python_source":
            text=source.get("content")
            if text is None:
                raw=path.read_bytes()
                if len(raw)>MAX_FILE_BYTES:raise ValueError("file_bytes_limit_exceeded")
                text=raw.decode("utf-8-sig")
            if not isinstance(text,str):raise ValueError("python_source_required")
            try:compile(text,relative,"exec");passed=True;detail="compiled"
            except (SyntaxError,ValueError,TypeError) as exc:passed=False;detail=f"{type(exc).__name__}:{getattr(exc,'lineno',None)}:{getattr(exc,'offset',None)}"
            result={"validation_type":"python_compile","relative_path":relative,"passed":passed,"detail":detail,"source_sha256":sha256(text.encode()).hexdigest(),"executed":False}
        else:
            needle=source.get("expected_text")
            if not isinstance(needle,str) or not needle:raise ValueError("expected_text_required")
            raw=path.read_bytes()
            if len(raw)>MAX_FILE_BYTES or b"\0" in raw:raise ValueError("invalid_text_file")
            text=raw.decode("utf-8-sig");result={"validation_type":"text_contains","relative_path":relative,"passed":needle in text,"expected_text_sha256":sha256(needle.encode()).hexdigest(),"source_sha256":sha256(raw).hexdigest(),"executed":False}
        value=_base(source,"completed",[],now);value["result"]=result;value["result_fingerprint"]=fingerprint({k:v for k,v in value.items() if k!="result_fingerprint"});return value
    except (OSError,UnicodeError,ValueError) as exc:return _base(source,"blocked",[str(exc)],now)

def create_tool_request(tool:str,relative_path:str,*,request_id:str,source_goal_id:str,source_session_id:str,execution_request_fingerprint:str,content:Any=None,operation:Any=None,expected_text:Any=None,now:Any=None)->dict[str,Any]:
    value={"contract":REQUEST_CONTRACT,"request_id":request_id,"tool":tool,"relative_path":relative_path,"source_goal_id":source_goal_id,"source_session_id":source_session_id,"execution_request_fingerprint":execution_request_fingerprint,"content":content,"operation":operation,"expected_text":expected_text,"created_at":time_text(now)}
    value["request_fingerprint"]=fingerprint(value);return value

__all__=["CONTRACT","MAX_CANDIDATE_BYTES","MAX_CANDIDATE_FILES","MAX_FILE_BYTES","REQUEST_CONTRACT","RESULT_CONTRACT","TOOLS","create_tool_request","execute_controlled_tool"]
