from __future__ import annotations
from copy import deepcopy
from typing import Any,Mapping
from core.engineering.engineering_intake_common import canonical_json,fingerprint,identified,identity_valid
from core.engineering.repository_analysis_common import ValidationResult

FORBIDDEN_KEYS=frozenset({"patch","diff","source_content","replacement_content","command","shell_command","executor","scheduler","runtime","mutation_adapter","authorization_token","execution_token"})
def approval_boundary(*,closed:bool=False,approval_granted:bool=False)->dict[str,Any]:
 return {"sealed":True,"read_only":True,"approval_artifact":True,"approval_closed":closed,"repository_modified":False,"patch_generated":False,"diff_generated":False,"execution_started":False,"runtime_activated":False,"approval_authority":"granted" if approval_granted else "not_granted","authorization_authority":"not_granted","execution_authority":"not_granted","mutation_authority":"not_granted"}
def contains_forbidden(value:Any)->bool:
 if isinstance(value,Mapping):return any((str(k).lower() in FORBIDDEN_KEYS and v not in (False,None,"not_granted")) or contains_forbidden(v) for k,v in value.items())
 if isinstance(value,list):return any(contains_forbidden(x) for x in value)
 return False
def approval_artifact(schema:str,status:str,payload:Mapping[str,Any],id_key:str,prefix:str,*,closed:bool=False,approval_granted:bool=False)->dict[str,Any]:
 return identified({"schema":schema,"status":status,**deepcopy(dict(payload)),"boundary":approval_boundary(closed=closed,approval_granted=approval_granted)},id_key,prefix)
def validate_approval_artifact(value:Any,*,schema:str,statuses:set[str],id_key:str,prefix:str,fields:set[str],closed:bool=False)->ValidationResult:
 if not isinstance(value,Mapping):return ValidationResult(False,("artifact_not_object",))
 required={"schema","status",id_key,"fingerprint","boundary",*fields};errors=[f"missing:{k}" for k in sorted(required-set(value))]+[f"unexpected:{k}" for k in sorted(set(value)-required)]
 if value.get("schema")!=schema or value.get("status") not in statuses:errors.append("invalid_contract")
 granted=closed and value.get("status")=="closed_approved"
 if value.get("boundary")!=approval_boundary(closed=closed,approval_granted=granted):errors.append("unsafe_boundary")
 if contains_forbidden(value):errors.append("forbidden_payload")
 try:
  if not identity_valid(value,id_key,prefix):errors.append("identity_mismatch")
 except (TypeError,ValueError):errors.append("identity_mismatch")
 return ValidationResult(not errors,tuple(dict.fromkeys(errors)))
def stable_record(payload:Mapping[str,Any],id_key:str,prefix:str)->dict[str,Any]:return identified(deepcopy(dict(payload)),id_key,prefix)
def validate_review_closure(v:Any)->ValidationResult:
 errors=[]
 if not isinstance(v,Mapping):return ValidationResult(False,("artifact_not_object",))
 if v.get("schema")!="zero.engineering.proposal_review_closure.v1" or v.get("status")!="closed":errors.append("review_closure_not_closed")
 try:
  if not identity_valid(v,"proposal_review_closure_id","engineering-proposal-review-closure-"):errors.append("review_closure_identity_mismatch")
 except (TypeError,ValueError):errors.append("review_closure_identity_mismatch")
 g=v.get("governance_boundary_declaration",{});n=v.get("next_boundary_declaration",{})
 if any(g.get(k) is True for k in ("authorization_granted","execution_granted","mutation_granted")):errors.append("upstream_authority_violation")
 if n.get("foundation")!="Engineering Approval Foundation" and n.get("permitted_destination")!="Engineering Approval Foundation":errors.append("invalid_next_boundary")
 return ValidationResult(not errors,tuple(dict.fromkeys(errors)))
__all__=["ValidationResult","approval_artifact","approval_boundary","canonical_json","contains_forbidden","fingerprint","stable_record","validate_approval_artifact","validate_review_closure"]
