from __future__ import annotations
import hashlib, json, re
from typing import Any, Mapping, Sequence

SCHEMAS={n:f"zero.engineering.{n}.v1" for n in (
"runtime_request","runtime_session","runtime_phase","runtime_admission","runtime_analysis_coordination",
"runtime_proposal_coordination","runtime_operator_pause","runtime_preparation_coordination",
"runtime_authorization_pause","runtime_transaction_coordination","runtime_execution_coordination",
"runtime_checkpoint","runtime_result","runtime_verification","runtime_evidence","runtime_closure")}
MODES=("preview","analyze","propose","prepare","authorize","execute","resume","inspect")
PHASES=("request_received","session_admitted","analysis_coordinated","proposal_coordinated",
"awaiting_operator_approval","operator_approval_verified","preparation_coordinated",
"awaiting_mutation_authorization","mutation_authorization_verified","transaction_coordinated",
"execution_ready","execution_started","execution_terminal","end_to_end_verified","closed")
TERMINAL_STATUSES=("succeeded","rejected","cancelled","failed_rolled_back","recovery_required","invalid")
SAFE_RELATIVE=re.compile(r"^(?![A-Za-z]:)(?![/\\])(?!.*(?:^|[/\\])\.\.(?:[/\\]|$))[A-Za-z0-9._/\\-]{1,512}$")
SENSITIVE=("credential","password","private_key","api_key","bearer","authorization_header","session_cookie","secret")
EXECUTABLE=("command","shell_fragment","executable_source","dynamic_import","adapter_object","callable")

def canonical_json(value:Any)->str: return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def fingerprint(value:Any)->str: return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
def reasons(values:Sequence[str])->list[str]: return sorted(set(x for x in values if x))
def artifact(kind:str,body:Mapping[str,Any],id_field:str|None=None)->dict[str,Any]:
    b={"schema":SCHEMAS[kind],**dict(body)}; fp=fingerprint(b); b["fingerprint"]=fp
    b[id_field or kind.replace("runtime_","")+"_id"]="er-"+kind.replace("runtime_","").replace("_","-")+"-"+fp[:24]
    return b
def ref(value:Mapping[str,Any])->dict[str,Any]:
    return {k:value.get(k) for k in value if k.endswith("_id") or k in ("schema","fingerprint","status")}
def validate_artifact(value:Any,schema:str|None=None)->list[str]:
    if not isinstance(value,dict): return ["artifact_invalid"]
    rs=[]
    if schema and value.get("schema")!=schema: rs.append("schema_invalid")
    base={k:v for k,v in value.items() if k!="fingerprint"}; candidates=[base]
    candidates += [{k:v for k,v in base.items() if k!=candidate} for candidate,v in base.items() if candidate.endswith("_id") and str(v).startswith("er-")]
    if value.get("fingerprint") not in {fingerprint(x) for x in candidates}: rs.append("fingerprint_mismatch")
    return reasons(rs)
def prohibited(value:Any)->list[str]:
    rs=[]
    def walk(v:Any):
        if callable(v): rs.append("callable_payload"); return
        if isinstance(v,(bytes,bytearray,memoryview)): rs.append("binary_payload"); return
        if isinstance(v,dict):
            for k,x in v.items():
                key=str(k).lower().replace("-","_")
                if any(t in key for t in SENSITIVE+EXECUTABLE): rs.append("prohibited_"+key)
                if key.endswith("path") and isinstance(x,str) and (x.startswith(("/","\\")) or re.match(r"^[A-Za-z]:",x)): rs.append("absolute_host_path")
                walk(x)
        elif isinstance(v,(list,tuple)):
            if len(v)>10000: rs.append("unbounded_sequence")
            for x in v: walk(x)
        elif isinstance(v,str) and len(v)>1_000_000: rs.append("unbounded_string")
    walk(value); return reasons(rs)
