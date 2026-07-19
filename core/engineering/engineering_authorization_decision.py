from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_authorization_intake import AUTH
from core.engineering.engineering_authorization_common import ValidationResult,authorization_artifact,validate_authorization_artifact
SCHEMA="zero.engineering.authorization_decision.v1";ID_KEY="authorization_decision_id";PREFIX="engineering-authorization-decision-";FIELDS={"authorization_intake_id","authorization_eligibility_id","authorization_policy_id","decision","rationale","blocking_conditions","authority_declarations"}
def build_engineering_authorization_decision(i:Mapping[str,Any],e:Mapping[str,Any],p:Mapping[str,Any])->dict[str,Any]:
 if i.get("status")!="accepted":d="invalid"
 elif e.get("status")=="insufficient_evidence":d="insufficient_evidence"
 elif e.get("status")!="eligible" or p.get("status")!="satisfied":d="denied"
 else:d="authorized" if i.get("requested_decision")=="authorize" else "denied"
 payload={"authorization_intake_id":i.get("authorization_intake_id"),"authorization_eligibility_id":e.get("authorization_eligibility_id"),"authorization_policy_id":p.get("authorization_policy_id"),"decision":d,"rationale":"deterministic eligibility and policy evaluation","blocking_conditions":e.get("blocking_conditions",[])+p.get("policy_findings",[]),"authority_declarations":dict(AUTH)};return authorization_artifact(SCHEMA,d,payload,ID_KEY,PREFIX)
def validate_engineering_authorization_decision(v:Any)->ValidationResult:return validate_authorization_artifact(v,schema=SCHEMA,statuses={"authorized","denied","blocked","invalid","insufficient_evidence"},id_key=ID_KEY,prefix=PREFIX,fields=FIELDS)
__all__=["build_engineering_authorization_decision","validate_engineering_authorization_decision"]
