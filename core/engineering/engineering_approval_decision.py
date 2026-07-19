from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_approval_intake import AUTH
from core.engineering.engineering_approval_common import ValidationResult,approval_artifact,validate_approval_artifact
SCHEMA="zero.engineering.approval_decision.v1";ID_KEY="approval_decision_id";PREFIX="engineering-approval-decision-";FIELDS={"approval_intake_id","approval_eligibility_id","approval_policy_id","decision","rationale","blocking_conditions","authority_declarations"}
def build_engineering_approval_decision(i:Mapping[str,Any],e:Mapping[str,Any],p:Mapping[str,Any])->dict[str,Any]:
 if i.get("status")!="accepted":d="invalid"
 elif e.get("status")=="insufficient_evidence":d="insufficient_evidence"
 elif e.get("status")!="eligible" or p.get("status")!="satisfied":d="rejected"
 else:d="approved" if i.get("requested_decision")=="approve" else "rejected"
 payload={"approval_intake_id":i.get("approval_intake_id"),"approval_eligibility_id":e.get("approval_eligibility_id"),"approval_policy_id":p.get("approval_policy_id"),"decision":d,"rationale":"deterministic eligibility and policy evaluation","blocking_conditions":e.get("blocking_conditions",[])+p.get("policy_findings",[]),"authority_declarations":dict(AUTH)};return approval_artifact(SCHEMA,d,payload,ID_KEY,PREFIX)
def validate_engineering_approval_decision(v:Any)->ValidationResult:return validate_approval_artifact(v,schema=SCHEMA,statuses={"approved","rejected","blocked","invalid","insufficient_evidence"},id_key=ID_KEY,prefix=PREFIX,fields=FIELDS)
__all__=["build_engineering_approval_decision","validate_engineering_approval_decision"]
