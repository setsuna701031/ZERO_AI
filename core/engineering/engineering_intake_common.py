from __future__ import annotations
from copy import deepcopy
import hashlib, json, math, re, unicodedata
from pathlib import PurePath
from typing import Any, Mapping

MAX_REQUEST_LENGTH = 8000
FORBIDDEN_KEYS = frozenset({"patch","diff","file_content","replacement_content","write_file","delete_file","rename_file","shell_command","executable_command","command","subprocess","callback","callable","handler","adapter_instance","provider_instance","plugin_instance","runtime_handle","executor","executor_target","scheduler","scheduler_queue","planner_instance","mission_instance","agent_instance","approval_token","authorization_token","admission_token","mutation_plan","execution_plan","runtime_started","environment_probe","absolute_path","credentials","secret"})
TRUE_FORBIDDEN = frozenset({"execution_started","coding_started","proposal_created","approval_granted","authorization_granted","mutation_allowed","authority_granted"})

def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
def fingerprint(value: Any) -> str: return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
def identified(base: Mapping[str, Any], id_key: str, prefix: str) -> dict[str, Any]:
    body=deepcopy(dict(base)); fp=fingerprint(body); return {**body,id_key:prefix+fp[:24],"fingerprint":fp}
def normalize_request(value: Any) -> str:
    if not isinstance(value,str): raise TypeError("developer_request_not_string")
    text=re.sub(r"\s+"," ",unicodedata.normalize("NFKC",value).replace("\u3000"," ")).strip()
    if not text: raise ValueError("empty_developer_request")
    if "\x00" in text: raise ValueError("nul_in_developer_request")
    if len(text)>MAX_REQUEST_LENGTH: raise ValueError("developer_request_too_long")
    return text
def unsafe(value: Any, *, raw_keys: frozenset[str]=frozenset({"normalized_request","mission_objective","engineering_objective"})) -> bool:
    if callable(value) or isinstance(value,(bytes,set,tuple,PurePath)): return True
    if isinstance(value,float) and not math.isfinite(value): return True
    if isinstance(value,Mapping):
        for k,v in value.items():
            if k in FORBIDDEN_KEYS or (k in TRUE_FORBIDDEN and v is True): return True
            if k not in raw_keys and unsafe(v,raw_keys=raw_keys): return True
        return False
    if isinstance(value,list): return any(unsafe(v,raw_keys=raw_keys) for v in value)
    if isinstance(value,str) and (any(x in value for x in ("\n","\r",";","|","&&","$(","`")) or re.search(r"(?:^|\s)(?:rm|del|powershell|cmd|bash|sh|pytest)(?:\s|$)",value,re.I)): return True
    return not (value is None or isinstance(value,(str,bool,int,float)))
def identity_valid(value: Mapping[str,Any], id_key:str, prefix:str)->bool:
    body={k:v for k,v in value.items() if k not in {id_key,"fingerprint"}}; expected=identified(body,id_key,prefix)
    return value.get(id_key)==expected[id_key] and value.get("fingerprint")==expected["fingerprint"]
def links(source: Any, direct_name:str, direct_id:str)->dict[str,Any]:
    v=source if isinstance(source,Mapping) else {}; out={f"source_{direct_name}_id":v.get(direct_id),f"source_{direct_name}_fingerprint":v.get("fingerprint")}
    out.update({k:v.get(k) for k in v if k.startswith("source_")}); return out
def source_status(source:Any)->Any:return source.get("status") if isinstance(source,Mapping) else None
def passive_boundary(kind:str,**extra:bool)->dict[str,bool]:
    return {"sealed":True,"read_only":True,kind:True,"repository_access":False,"planning_started":False,"proposal_created":False,"coding_started":False,"execution_started":False,"mutation_allowed":False,"runtime_activation":False,"authority_granted":False,"scope_expansion":False,**extra}
def generic_validate(value:Any,required:set[str],schema:str,statuses:set[str],id_key:str,prefix:str,boundary:Mapping[str,bool])->list[str]:
    if not isinstance(value,Mapping):return ["artifact_not_object"]
    errors=[f"missing:{k}" for k in sorted(required-set(value))]+[f"unexpected:{k}" for k in sorted(set(value)-required)]
    if value.get("schema")!=schema or value.get("status") not in statuses:errors.append("invalid_contract")
    if value.get("boundary")!=boundary:errors.append("unsafe_boundary")
    if unsafe(value):errors.append("forbidden_content")
    try:ok=identity_valid(value,id_key,prefix)
    except (TypeError,ValueError):ok=False
    if not ok:errors.append("identity_mismatch")
    return list(dict.fromkeys(errors))

__all__=["MAX_REQUEST_LENGTH","canonical_json","fingerprint","identified","normalize_request","unsafe","identity_valid","links","source_status","passive_boundary","generic_validate"]
