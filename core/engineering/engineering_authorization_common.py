from __future__ import annotations
from copy import deepcopy
from typing import Any,Mapping
from core.engineering.engineering_intake_common import canonical_json,fingerprint,identified,identity_valid
from core.engineering.repository_analysis_common import ValidationResult

FORBIDDEN_KEYS=frozenset({"patch","diff","source_content","replacement_content","command","shell_command","executor","scheduler","runtime","mutation_adapter","execution_token"})
def authorization_boundary(*,closed:bool=False,authorization_granted:bool=False)->dict[str,Any]:
 return {"sealed":True,"read_only":True,"authorization_artifact":True,"authorization_closed":closed,"repository_modified":False,"patch_generated":False,"diff_generated":False,"runtime_invoked":False,"execution_started":False,"approval_authority":"granted","authorization_authority":"granted" if authorization_granted else "not_granted","execution_authority":"not_granted","mutation_authority":"not_granted"}
def contains_forbidden(value:Any)->bool:
 if isinstance(value,Mapping):return any(str(k).lower() in FORBIDDEN_KEYS or contains_forbidden(v) for k,v in value.items())
 if isinstance(value,list):return any(contains_forbidden(x) for x in value)
 return False
def authorization_artifact(schema:str,status:str,payload:Mapping[str,Any],id_key:str,prefix:str,*,closed:bool=False,authorization_granted:bool=False)->dict[str,Any]:
 return identified({"schema":schema,"status":status,**deepcopy(dict(payload)),"boundary":authorization_boundary(closed=closed,authorization_granted=authorization_granted)},id_key,prefix)
def validate_authorization_artifact(value:Any,*,schema:str,statuses:set[str],id_key:str,prefix:str,fields:set[str],closed:bool=False)->ValidationResult:
 if not isinstance(value,Mapping):return ValidationResult(False,("artifact_not_object",))
 required={"schema","status",id_key,"fingerprint","boundary",*fields};errors=[f"missing:{k}" for k in sorted(required-set(value))]+[f"unexpected:{k}" for k in sorted(set(value)-required)]
 if value.get("schema")!=schema or value.get("status") not in statuses:errors.append("invalid_contract")
 granted=closed and value.get("status")=="closed_authorized"
 if value.get("boundary")!=authorization_boundary(closed=closed,authorization_granted=granted):errors.append("unsafe_boundary")
 if contains_forbidden(value):errors.append("forbidden_payload")
 try:
  if not identity_valid(value,id_key,prefix):errors.append("identity_mismatch")
 except (TypeError,ValueError):errors.append("identity_mismatch")
 return ValidationResult(not errors,tuple(dict.fromkeys(errors)))
def stable_record(payload:Mapping[str,Any],id_key:str,prefix:str)->dict[str,Any]:return identified(deepcopy(dict(payload)),id_key,prefix)
def validate_approval_closure(v:Any)->ValidationResult:
 errors=[]
 if not isinstance(v,Mapping):return ValidationResult(False,("artifact_not_object",))
 if v.get("schema")!="zero.engineering.approval_closure.v1" or v.get("status")!="closed_approved":errors.append("approval_closure_not_approved")
 try:
  if not identity_valid(v,"approval_closure_id","engineering-approval-closure-"):errors.append("approval_closure_identity_mismatch")
 except (TypeError,ValueError):errors.append("approval_closure_identity_mismatch")
 b=v.get("boundary",{})
 if b.get("approval_authority")!="granted" or b.get("authorization_authority")!="not_granted" or b.get("execution_authority")!="not_granted" or b.get("mutation_authority")!="not_granted":errors.append("approval_authority_boundary_mismatch")
 return ValidationResult(not errors,tuple(dict.fromkeys(errors)))
__all__=["ValidationResult","authorization_artifact","authorization_boundary","canonical_json","contains_forbidden","fingerprint","stable_record","validate_approval_closure","validate_authorization_artifact"]
