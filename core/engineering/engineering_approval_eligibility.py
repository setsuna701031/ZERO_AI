from __future__ import annotations
from typing import Any,Mapping
from core.engineering.engineering_approval_common import ValidationResult,approval_artifact,validate_approval_artifact
SCHEMA="zero.engineering.approval_eligibility.v1";ID_KEY="approval_eligibility_id";PREFIX="engineering-approval-eligibility-";FIELDS={"approval_intake_id","checks","blocking_conditions","evidence_gaps","eligibility"}
def build_engineering_approval_eligibility(i:Mapping[str,Any],intent:Mapping[str,Any]|None=None)->dict[str,Any]:
 x=dict(intent or {});gaps=sorted(set(x.get("evidence_gaps",[])));blocks=sorted(set(x.get("eligibility_blocks",[])));eligible=i.get("status")=="accepted" and not gaps and not blocks;p={"approval_intake_id":i.get("approval_intake_id"),"checks":{"intake_accepted":i.get("status")=="accepted","review_closure_linked":bool(i.get("proposal_review_closure_id")),"evidence_sufficient":not gaps,"authority_absent":True},"blocking_conditions":blocks,"evidence_gaps":gaps,"eligibility":"eligible" if eligible else ("insufficient_evidence" if gaps else "not_eligible")};return approval_artifact(SCHEMA,p["eligibility"],p,ID_KEY,PREFIX)
def validate_engineering_approval_eligibility(v:Any)->ValidationResult:return validate_approval_artifact(v,schema=SCHEMA,statuses={"eligible","not_eligible","blocked","invalid","insufficient_evidence"},id_key=ID_KEY,prefix=PREFIX,fields=FIELDS)
__all__=["build_engineering_approval_eligibility","validate_engineering_approval_eligibility"]
