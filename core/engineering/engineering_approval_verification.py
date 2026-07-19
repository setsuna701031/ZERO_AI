from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_approval_common import ValidationResult,approval_artifact,validate_approval_artifact
from core.engineering.engineering_approval_decision import validate_engineering_approval_decision
SCHEMA="zero.engineering.approval_verification.v1";ID_KEY="approval_verification_id";PREFIX="engineering-approval-verification-";FIELDS={"approval_decision_id","approval_conditions_id","checks","errors","warnings","verified_decision"}
def verify_engineering_approval(d:Mapping[str,Any],c:Mapping[str,Any])->dict[str,Any]:
 checks={"decision_contract":validate_engineering_approval_decision(d).valid,"conditions_resolved":c.get("status")=="satisfied","approval_not_granted_before_closure":d.get("boundary",{}).get("approval_authority")=="not_granted","authorization_not_granted":d.get("boundary",{}).get("authorization_authority")=="not_granted","execution_not_granted":d.get("boundary",{}).get("execution_authority")=="not_granted","mutation_not_granted":d.get("boundary",{}).get("mutation_authority")=="not_granted"};errors=sorted(k for k,v in checks.items() if not v);status="verified" if not errors else "invalid";p={"approval_decision_id":d.get("approval_decision_id"),"approval_conditions_id":c.get("approval_conditions_id"),"checks":[{"name":k,"passed":v} for k,v in sorted(checks.items())],"errors":errors,"warnings":[],"verified_decision":d.get("decision")};return approval_artifact(SCHEMA,status,p,ID_KEY,PREFIX)
def validate_engineering_approval_verification(v:Any)->ValidationResult:return validate_approval_artifact(v,schema=SCHEMA,statuses={"verified","blocked","invalid"},id_key=ID_KEY,prefix=PREFIX,fields=FIELDS)
__all__=["verify_engineering_approval","validate_engineering_approval_verification"]
