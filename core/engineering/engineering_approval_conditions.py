from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_approval_common import ValidationResult,approval_artifact,stable_record,validate_approval_artifact
SCHEMA="zero.engineering.approval_conditions.v1";ID_KEY="approval_conditions_id";PREFIX="engineering-approval-conditions-";FIELDS={"approval_intake_id","conditions","unresolved_conditions","condition_outcome"}
def build_engineering_approval_conditions(i:Mapping[str,Any],intent:Mapping[str,Any]|None=None)->dict[str,Any]:
 x=dict(intent or {});raw=x.get("conditions",[]);conditions=[]
 for value in sorted(set(raw)):
  conditions.append(stable_record({"description":value,"bounded":True,"authorization_effect":"none","execution_effect":"none","mutation_effect":"none","status":"satisfied" if value in set(x.get("satisfied_conditions",raw)) else "unresolved"},"approval_condition_id","engineering-approval-condition-"))
 unresolved=[c["approval_condition_id"] for c in conditions if c["status"]=="unresolved"];outcome="satisfied" if not unresolved else "unresolved";return approval_artifact(SCHEMA,outcome,{"approval_intake_id":i.get("approval_intake_id"),"conditions":conditions,"unresolved_conditions":unresolved,"condition_outcome":outcome},ID_KEY,PREFIX)
def validate_engineering_approval_conditions(v:Any)->ValidationResult:return validate_approval_artifact(v,schema=SCHEMA,statuses={"satisfied","unresolved","blocked","invalid"},id_key=ID_KEY,prefix=PREFIX,fields=FIELDS)
__all__=["build_engineering_approval_conditions","validate_engineering_approval_conditions"]
