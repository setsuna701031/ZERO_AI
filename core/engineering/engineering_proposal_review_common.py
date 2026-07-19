from __future__ import annotations
from copy import deepcopy
from typing import Any, Mapping

from core.engineering.engineering_intake_common import canonical_json, fingerprint, identified, identity_valid
from core.engineering.engineering_planning_common import ValidationResult
from core.engineering.engineering_proposal_common import contains_forbidden_payload

DECISIONS=("ready_for_approval","changes_requested","blocked","invalid","insufficient_evidence")
SEVERITIES=("informational","low","medium","high","critical","unknown")
FINDING_CATEGORIES=("evidence","scope","dependency","validation","risk","governance","integrity","compatibility","ambiguity")
AUTHORITY={"approval_authority":"not_granted","authorization_authority":"not_granted","execution_authority":"not_granted","mutation_authority":"not_granted"}

def review_boundary()->dict[str,bool]:
 return {"sealed":True,"read_only":True,"repository_modified":False,"proposal_modified":False,"patch_generated":False,"diff_generated":False,"source_payload_generated":False,"execution_started":False,"mutation_allowed":False,"approval_granted":False,"authorization_granted":False,"authority_granted":False}

def review_artifact(schema:str,status:str,payload:Mapping[str,Any],id_key:str,prefix:str)->dict[str,Any]:
 return identified({"schema":schema,"status":status,**deepcopy(dict(payload)),"boundary":review_boundary()},id_key,prefix)

def validate_review_artifact(value:Any,*,schema:str,statuses:set[str],id_key:str,prefix:str,fields:set[str])->ValidationResult:
 if not isinstance(value,Mapping): return ValidationResult(False,("artifact_not_object",))
 required={"schema","status",id_key,"fingerprint","boundary",*fields}; errors=[]
 errors += [f"missing:{x}" for x in sorted(required-set(value))]
 errors += [f"unexpected:{x}" for x in sorted(set(value)-required)]
 if value.get("schema")!=schema or value.get("status") not in statuses: errors.append("invalid_contract")
 if value.get("boundary")!=review_boundary(): errors.append("unsafe_boundary")
 if contains_forbidden_payload(value): errors.append("forbidden_payload")
 try:
  if not identity_valid(value,id_key,prefix): errors.append("identity_mismatch")
 except (TypeError,ValueError): errors.append("identity_mismatch")
 return ValidationResult(not errors,tuple(dict.fromkeys(errors)))

def stable_record(payload:Mapping[str,Any],id_key:str,prefix:str)->dict[str,Any]: return identified(deepcopy(dict(payload)),id_key,prefix)
def closure_linkage(c:Mapping[str,Any])->dict[str,Any]:
 return {k:c.get(k) for k in ("proposal_closure_id","engineering_proposal_id","planning_closure_id","repository_identity","analyzed_revision")}
def authority_absent(value:Any)->bool:
 if isinstance(value,Mapping):
  for k,v in value.items():
   if k in {"approved","authorized","executable","mutation_granted"} and v is True:return False
   if k in {"approval_authority","authorization_authority","execution_authority","mutation_authority"} and v not in (None,False,"not_granted"):return False
   if not authority_absent(v):return False
 elif isinstance(value,list): return all(authority_absent(x) for x in value)
 return True

__all__=["AUTHORITY","DECISIONS","FINDING_CATEGORIES","SEVERITIES","ValidationResult","authority_absent","canonical_json","closure_linkage","fingerprint","review_artifact","review_boundary","stable_record","validate_review_artifact"]
